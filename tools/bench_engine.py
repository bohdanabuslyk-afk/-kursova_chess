"""Швидкість рушія на фіксованих позиціях: python -m tools.bench_engine [секунд]"""
import sys

import chess

from app.engine import Engine

POSITIONS = {
    "початкова": chess.STARTING_FEN,
    "мітельшпіль": "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 9",
    "гостра (Вічнозелена, 16-й хід)": "1r2k2r/pbppnppp/1bn5/4P2q/Q3N3/B1PB1N2/P4PPP/R3R1K1 w k - 1 17",
    "ендшпіль": "8/5k2/3p4/1P6/4K3/8/6R1/8 w - - 0 1",
}

if __name__ == "__main__":
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    for name, fen in POSITIONS.items():
        r = Engine().search(chess.Board(fen), 30, seconds)
        print(f"{name:32} глибина {r.depth:2}  вузлів {r.nodes:7}  вузлів/с {r.nodes / max(r.seconds, .01):8.0f}  {r.move.uci()}  {r.score}")
