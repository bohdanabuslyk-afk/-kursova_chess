import random
import unittest

import chess

from app.engine import LEVELS, Engine, choose_move, evaluate


class Evaluation(unittest.TestCase):
    def test_start_is_balanced(self):
        self.assertEqual(evaluate(chess.Board()), 0)

    def test_mirror_symmetry(self):
        """Дзеркальна позиція має ту саму оцінку – таблиці обох кольорів узгоджені."""
        for fen in ("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
                    "8/5k2/3p4/1P6/4K3/8/6R1/8 b - - 0 1"):
            b = chess.Board(fen)
            self.assertEqual(evaluate(b), evaluate(b.mirror()))

    def test_extra_queen(self):
        self.assertGreater(evaluate(chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")), 700)


class Search(unittest.TestCase):
    def best(self, fen, depth=4, seconds=10):
        return Engine().search(chess.Board(fen), depth, seconds)

    def test_mate_in_one(self):
        r = self.best("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        self.assertEqual((r.move.uci(), r.mate_in), ("a1a8", 1))

    def test_mate_in_two(self):
        r = self.best("7k/8/8/8/8/8/R7/1R2K3 w - - 0 1")
        self.assertEqual(r.mate_in, 2)

    def test_being_mated_is_negative(self):
        self.assertLess(self.best("R5k1/5ppp/8/8/8/8/8/4K3 b - - 0 1").score, -90_000)

    def test_takes_hanging_queen(self):
        self.assertEqual(self.best("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1").move.uci(), "e4d5")

    def test_does_not_take_protected_pawn_with_queen(self):
        r = self.best("4k3/2p5/3p4/8/8/8/3Q4/4K3 w - - 0 1", depth=2)
        self.assertNotEqual(r.move.uci(), "d2d6")

    def test_avoids_stalemate(self):
        b = chess.Board("7k/8/5K2/8/8/8/8/6Q1 w - - 0 1")
        b.push(self.best(b.fen()).move)
        self.assertFalse(b.is_stalemate())

    def test_time_limit(self):
        r = Engine().search(chess.Board("r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 9"), 30, 1.0)
        self.assertLess(r.seconds, 1.6)
        self.assertGreaterEqual(r.depth, 1)

    def test_pv_is_legal(self):
        b = chess.Board()
        for m in Engine().search(b, 4, 5).pv:
            self.assertIn(m, b.legal_moves)
            b.push(m)

    def test_board_not_modified(self):
        b = chess.Board()
        fen = b.fen()
        Engine().search(b, 5, 0.3)
        self.assertEqual(b.fen(), fen)


class Levels(unittest.TestCase):
    def test_every_level_returns_legal_move(self):
        b = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        for level in (1, 2, 3, 4):
            self.assertIn(choose_move(b, level, random.Random(1)).move, b.legal_moves)
        self.assertEqual(set(LEVELS), {1, 2, 3, 4, 5})


if __name__ == "__main__":
    unittest.main()
