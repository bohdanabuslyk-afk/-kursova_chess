import unittest

import chess

from app.analysis import Analysis, classify, hanging, move_accuracy, score_text, win_percent
from app.engine import MATE


def analyse(*sans):
    b = chess.Board()
    for s in sans:
        b.push_san(s)
    a = Analysis(b)
    a.seconds = 0.15
    a.run()
    return a


class Formulas(unittest.TestCase):
    def test_win_percent(self):
        self.assertEqual(win_percent(0), 50)
        self.assertAlmostEqual(win_percent(150) + win_percent(-150), 100)
        self.assertEqual((win_percent(MATE - 3), win_percent(-MATE + 3)), (100, 0))

    def test_accuracy_bounds(self):
        self.assertAlmostEqual(move_accuracy(0), 100, delta=0.01)
        self.assertEqual(move_accuracy(100), 0)
        self.assertGreater(move_accuracy(5), move_accuracy(15))

    def test_classes(self):
        got = [classify(x, False, False, False) for x in (0.5, 3, 7, 15, 40)]
        self.assertEqual(got, ["best", "good", "inacc", "mistake", "blunder"])
        self.assertEqual(classify(50, False, False, True), "forced")
        self.assertEqual(classify(2, False, True, False), "book")
        self.assertEqual(classify(30, False, True, False), "blunder")

    def test_score_text(self):
        self.assertEqual(score_text(-135), "−1.35")
        self.assertEqual(score_text(MATE - 3), "+М2")
        self.assertEqual(score_text(-MATE), "0–1")

    def test_hanging(self):
        self.assertEqual(hanging(chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1"), chess.BLACK), ["ферзь d5"])


class WholeGame(unittest.TestCase):
    def test_fools_mate(self):
        a = analyse("f3", "e5", "g4", "Qh4#")
        self.assertEqual(a.rows[2]["class"], "blunder")
        self.assertEqual(a.rows[2]["best"] == "g4", False)
        self.assertEqual(a.rows[3]["class"], "best")
        self.assertEqual(a.rows[3]["scoreText"], "0–1")
        self.assertIn("Мат", a.rows[3]["facts"][0])
        self.assertIn(3, a.summary["moments"])
        self.assertGreater(a.summary["black"]["accuracy"], a.summary["white"]["accuracy"])
        self.assertEqual(a.done, a.total)

    def test_hung_queen_is_blunder(self):
        a = analyse("e4", "e5", "Qh5", "Nc6", "Qxh7", "Rxh7")
        self.assertEqual(a.rows[4]["class"], "blunder")
        self.assertGreater(a.rows[5]["accuracy"], 95)

    def test_book_moves(self):
        a = analyse("e4", "e5", "Nf3", "Nc6")
        self.assertEqual({r["class"] for r in a.rows}, {"book"})

    def test_empty_game(self):
        a = analyse()
        self.assertEqual(a.rows, [])
        self.assertIsNone(a.summary["white"]["accuracy"])


if __name__ == "__main__":
    unittest.main()
