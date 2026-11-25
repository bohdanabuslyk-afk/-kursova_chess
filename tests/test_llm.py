"""LLM-модуль: перевірка на підставній моделі, без мережі та ключів."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import chess

from app import llm as L
from app.game import Game
from tools import mock_llm


class Fake(L.LLM):
    """Модель, що відповідає за заготовленим списком."""

    def __init__(self, *answers):
        super().__init__(L.Config("http://x", "k", "fake"))
        self.answers, self.calls = list(answers), []

    def ask(self, messages):
        self.calls.append([dict(m) for m in messages])
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(L, "LOG", Path(tmp.name) / "log.jsonl")
        p.start()
        self.addCleanup(p.stop)


class Json(unittest.TestCase):
    def test_variants(self):
        for t in ('{"move":"e2e4"}', '```json\n{"move": "e2e4"}\n```', 'Думаю {так}: {"move":"e2e4"} ок'):
            self.assertEqual(L.extract_json(t), {"move": "e2e4"})
        self.assertIsNone(L.extract_json("хід e4"))


class Opponent(Base):
    def test_good_answer(self):
        move, info = L.llm_move(chess.Board(), 3, Fake('{"move":"e2e4","comment":"Центр"}'))
        self.assertEqual((move.uci(), info["comment"], info["attempts"], info["fallback"]), ("e2e4", "Центр", 1, False))

    def test_san_is_accepted(self):
        self.assertEqual(L.llm_move(chess.Board(), 3, Fake('{"move":"Nf3"}'))[0].uci(), "g1f3")

    def test_illegal_then_fixed(self):
        f = Fake('{"move":"e2e5"}', "не json", '{"move":"d2d4"}')
        move, info = L.llm_move(chess.Board(), 2, f)
        self.assertEqual((move.uci(), info["attempts"], len(info["errors"])), ("d2d4", 3, 2))
        self.assertIn("не прийнято", f.calls[1][-1]["content"])

    def test_three_failures_use_engine(self):
        move, info = L.llm_move(chess.Board(), 3, Fake(*['{"move":"a1a8"}'] * 3))
        self.assertIn(move, chess.Board().legal_moves)
        self.assertTrue(info["fallback"])

    def test_service_down_uses_engine_at_once(self):
        f = Fake(L.LLMError("Немає зв'язку"))
        move, info = L.llm_move(chess.Board(), 3, f)
        self.assertIn(move, chess.Board().legal_moves)
        self.assertEqual((info["fallback"], len(f.calls)), (True, 1))

    def test_hybrid_offers_only_top_moves(self):
        b = chess.Board("4k3/8/8/3q4/4P3/8/8/4K2R w K - 0 1")
        f = Fake('{"move":"h1h2"}', '{"move":"e4d5"}')
        move, _ = L.llm_move(b, 5, f)
        self.assertEqual(move.uci(), "e4d5")
        self.assertEqual(f.calls[0][1]["content"].split("Дозволені ходи:")[1].count("("), 3)

    def test_null_move_rejected(self):
        for bad in ("0000", "--", "", None):
            m, _, why = L.read_move(chess.Board(), L.json.dumps({"move": bad}), list(chess.Board().legal_moves))
            self.assertIsNone(m)
            self.assertTrue(why)

    def test_game_uses_llm(self):
        g = Game("white", "llm", 2)
        g.play("e4")
        with mock.patch.object(L, "llm", Fake('{"move":"e7e5","comment":"Так"}')):
            g.reply()
        self.assertEqual(g.state()["history"][1]["san"], "e5")
        self.assertEqual(g.info["by"], "llm")


ROW = {"color": "white", "san": "Qh5", "uci": "d1h5", "best": "Nf3", "bestUci": "g1f3", "bestLine": "2. Nf3 Nc6",
       "bestScoreText": "+0.30", "scoreText": "−0.20", "className": "неточність", "facts": ["Хід нападає."]}


class Explain(Base):
    def test_template_without_model(self):
        r = L.explain(chess.Board(), ROW, L.LLM(L.Config()))
        self.assertEqual((r["by"], r["text"]), ("template", "Хід нападає."))

    def test_model_text(self):
        r = L.explain(chess.Board(), ROW, Fake("Краще Nf3, розвиток."))
        self.assertEqual((r["by"], r["warning"]), ("llm", None))

    def test_invented_move_is_flagged(self):
        self.assertIn("Bxf7", L.explain(chess.Board(), ROW, Fake("Грозить Bxf7 і Nf3."))["warning"])

    def test_failure_falls_back(self):
        r = L.explain(chess.Board(), ROW, Fake(L.LLMError("збій")))
        self.assertEqual((r["by"], r["warning"]), ("template", "збій"))


class Http(Base):
    """Справжній HTTP-запит через SDK до локальної заглушки."""

    def test_round_trip(self):
        server = mock_llm.serve(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        model = L.LLM(L.Config(f"http://127.0.0.1:{server.server_port}/v1", "test", "mock", 10))
        move, info = L.llm_move(chess.Board(), 1, model)
        self.assertFalse(info["fallback"])
        self.assertIn(move, chess.Board().legal_moves)
        self.assertIn("заглушка", L.chat(chess.Board(), [], "Що робити?", model))

    def test_no_connection(self):
        model = L.LLM(L.Config("http://127.0.0.1:9/v1", "test", "mock", 2))
        with self.assertRaisesRegex(L.LLMError, "зв'язку|вчасно"):
            model.ask([{"role": "user", "content": "?"}])

    def test_key_is_not_exposed(self):
        self.assertNotIn("secret", str(L.LLM(L.Config("http://x", "secret", "m")).status()))


if __name__ == "__main__":
    unittest.main()
