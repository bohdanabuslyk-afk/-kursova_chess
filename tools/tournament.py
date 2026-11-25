"""Турнір рівнів складності між собою: python -m tools.tournament [партій] [процесів]

Кожна пара сусідніх рівнів грає однакову кількість партій білими й чорними з випадкових
дебютів довідника. Результат: docs/data/turnir_rivniv.json та .md
"""
from __future__ import annotations

import json
import math
import random
import sys
from multiprocessing import Pool
from pathlib import Path

import chess

from app.engine import LEVELS, choose_move
from app.openings import BOOK

OUT = Path(__file__).resolve().parent.parent / "docs" / "data"
LIMIT = 200  # півходів; довша партія – нічия


def play(task: tuple[int, int, int]) -> tuple[int, int, float, int]:
    """(нижчий рівень, вищий рівень, очки вищого, півходів)."""
    low, high, seed = task
    rng = random.Random(seed // 2)  # однаковий дебют двічі – по разу кожним кольором
    board = chess.Board()
    for san in rng.choice([line for line in BOOK if len(line) >= 4])[:4]:
        board.push_san(san)
    rng = random.Random(seed * 7919)
    high_white = seed % 2 == 0
    while not board.is_game_over(claim_draw=True) and board.ply() < LIMIT:
        level = high if board.turn == high_white else low
        board.push(choose_move(board, level, rng).move)
    result = board.result(claim_draw=True)
    if result not in ("1-0", "0-1"):
        return low, high, 0.5, board.ply()
    return low, high, float((result == "1-0") == high_white), board.ply()


def elo(score: float) -> str:
    if score in (0.0, 1.0):
        return "не визначено (усі партії одного суперника)"
    return f"{-400 * math.log10(1 / score - 1):+.0f}"


def main() -> None:
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    tasks = [(a, a + 1, i) for a in range(1, 5) for i in range(games)]
    table: dict[tuple[int, int], list] = {}
    with Pool(procs) as pool:
        for low, high, points, plies in pool.imap_unordered(play, tasks):
            table.setdefault((low, high), []).append((points, plies))
            print(low, high, points, plies, flush=True)
    rows = []
    for (low, high), res in sorted(table.items()):
        pts = [p for p, _ in res]
        rows.append({
            "вищий": LEVELS[high].name, "нижчий": LEVELS[low].name, "партій": len(pts),
            "перемог": pts.count(1.0), "нічиїх": pts.count(0.5), "поразок": pts.count(0.0),
            "очки_%": round(100 * sum(pts) / len(pts), 1), "різниця_Elo": elo(sum(pts) / len(pts)),
            "середня_довжина_півходів": round(sum(n for _, n in res) / len(res)),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "turnir_rivniv.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    head = list(rows[0])
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    md += ["| " + " | ".join(str(r[h]) for h in head) + " |" for r in rows]
    (OUT / "turnir_rivniv.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
