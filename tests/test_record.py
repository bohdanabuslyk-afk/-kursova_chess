"""Запис ходів, скасування, PGN, архів."""
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import chess

from app import storage
from app.game import Game, MoveError
from app.openings import BOOK, book_move, book_plies, opening_name


def played(*moves, **kw):
    g = Game(**kw)
    for m in moves:
        g.play(m)
    return g


class Undo(unittest.TestCase):
    def test_undo_two_players(self):
        g = played("e4", "e5")
        g.undo()
        self.assertEqual([r["san"] for r in g.history()], ["e4"])

    def test_undo_removes_reply_too(self):
        g = Game("white", "engine", 1)
        g.play("e4")
        g.reply()
        g.undo()
        self.assertEqual(g.history(), [])

    def test_undo_while_opponent_thinks(self):
        g = Game("white", "engine", 1)
        g.play("e4")
        g.undo()
        self.assertEqual(g.history(), [])

    def test_black_cannot_undo_opponents_first_move(self):
        g = Game("black", "engine", 1)
        with self.assertRaises(MoveError):
            g.undo()
        g.reply()
        with self.assertRaises(MoveError):
            g.undo()

    def test_stale_reply_is_dropped(self):
        """Відповідь, порахована до скасування, не потрапляє на дошку."""
        g = Game("white", "engine", 1)
        g.play("e4")
        original = g._think

        def slow(board):
            result = original(board)
            g.undo()
            return result

        with mock.patch.object(g, "_think", slow):
            g.reply()
        self.assertEqual(g.history(), [])


class Resign(unittest.TestCase):
    def test_resign(self):
        g = Game("black", "engine", 1)
        g.resign()
        self.assertEqual(g.outcome(), ("1-0", "чорні здалися"))
        g.undo()
        self.assertIsNone(g.outcome()[0])


class Pgn(unittest.TestCase):
    def test_round_trip(self):
        g = played("e4", "c5", "Nf3", "d6")
        g2 = Game.from_pgn(g.pgn())
        self.assertEqual(g2.board.fen(), g.board.fen())
        self.assertEqual(g2.state()["opening"], "Сицилійський захист")
        self.assertEqual(g2.state()["legal"], {})

    def test_settings_survive(self):
        g = Game("black", "engine", 4)
        g.reply()
        g2 = Game.from_pgn(g.pgn(), imported=False)
        self.assertEqual((g2.color, g2.opponent, g2.level), ("black", "engine", 4))

    def test_garbage(self):
        for text in ("", "просто текст", "1. e4 e5 2. Ke5", '[FEN "8/8/8/8/8/8/8/K6k w - - 0 1"]\n[SetUp "1"]\n\n1. Ka2 *'):
            with self.assertRaises(MoveError):
                Game.from_pgn(text)


class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(storage, "FOLDER", Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def test_save_load_list(self):
        g = played("e4", "e5")
        storage.save(g)
        self.assertEqual(storage.load(g.id).board.fen(), g.board.fen())
        row = storage.listing()[0]
        self.assertEqual((row["id"], row["moves"], row["result"]), (g.id, 1, "*"))

    def test_path_traversal(self):
        for bad in ("../../.env", "..\\x", "", "zzz"):
            self.assertIsNone(storage.load(bad))


class Openings(unittest.TestCase):
    def test_names(self):
        self.assertEqual(opening_name("e4 e5 Nf3 Nc6 Bb5".split()), "Іспанська партія")
        self.assertEqual(opening_name("e4 c5 a3 a6".split()), "Сицилійський захист")
        self.assertIsNone(opening_name(["h4"]))

    def test_book_move(self):
        self.assertIn(book_move([], random.Random(1)), ("e4", "d4", "c4", "Nf3", "f4", "b3"))
        self.assertIsNone(book_move(["h4"], random.Random(1)))

    def test_every_book_line_is_legal(self):
        for line in BOOK:
            b = chess.Board()
            for san in line:
                b.push_san(san)

    def test_book(self):
        self.assertEqual(book_plies("e4 e5 Nf3 h5".split()), 3)
        self.assertEqual(book_plies([]), 0)


if __name__ == "__main__":
    unittest.main()
