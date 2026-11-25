import unittest

import chess

from app.game import Game, MoveError, parse_move


class ParseMove(unittest.TestCase):
    def test_uci_and_san(self):
        b = chess.Board()
        for text in ("e2e4", "E2-E4", "e4"):
            self.assertEqual(parse_move(b, text).uci(), "e2e4")
        self.assertEqual(parse_move(b, "Nf3").uci(), "g1f3")

    def test_castling_with_zeros(self):
        b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertEqual(parse_move(b, "0-0").uci(), "e1g1")
        self.assertEqual(parse_move(b, "0-0-0").uci(), "e1c1")

    def test_ukrainian_notation(self):
        b = chess.Board("4k3/8/8/8/8/8/3P4/R2QKBN1 w Q - 0 1")
        for text, uci in (("Кf3", "g1f3"), ("Крe2", "e1e2"), ("Фb3", "d1b3"), ("Тa8+", "a1a8"), ("Сg2", "f1g2")):
            self.assertEqual(parse_move(b, text).uci(), uci)

    def test_promotion(self):
        b = chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        self.assertEqual(parse_move(b, "a7a8n").promotion, chess.KNIGHT)

    def test_illegal(self):
        for text in ("e2e5", "", "абв", "Ke2", "0000", "--"):
            with self.assertRaises(MoveError):
                parse_move(chess.Board(), text)


class GameRules(unittest.TestCase):
    def test_fools_mate(self):
        g = Game()
        for m in ("f3", "e5", "g4", "Qh4"):
            g.play(m)
        s = g.state()
        self.assertEqual((s["result"], s["reason"]), ("0-1", "мат"))
        self.assertEqual(s["legal"], {})
        with self.assertRaises(MoveError):
            g.play("a3")

    def test_en_passant(self):
        g = Game()
        for m in ("e4", "a6", "e5", "d5", "exd6"):
            g.play(m)
        self.assertIsNone(g.board.piece_at(chess.D5))

    def test_threefold(self):
        g = Game()
        for m in ["Nf3", "Nf6", "Ng1", "Ng8"] * 2:
            g.play(m)
        self.assertEqual(g.state()["result"], "1/2-1/2")


class Opponent(unittest.TestCase):
    def test_computer_moves_first_when_player_is_black(self):
        g = Game("black", "engine", 1)
        self.assertEqual(g.state()["legal"], {})
        with self.assertRaises(MoveError):
            g.play("e4")
        g.reply()
        self.assertEqual(len(g.board.move_stack), 1)
        self.assertTrue(g.players_turn)

    def test_reply_does_nothing_on_players_turn(self):
        g = Game("white", "engine", 1)
        g.reply()
        self.assertEqual(len(g.board.move_stack), 0)

    def test_random_color(self):
        self.assertIn(Game("random").color, ("white", "black"))

    def test_bad_settings(self):
        for args in (("red",), ("white", "x"), ("white", "engine", 9)):
            with self.assertRaises(MoveError):
                Game(*args)


if __name__ == "__main__":
    unittest.main()
