"""Вимірювання мовної моделі: python -m tools.llm_benchmark [позицій]

Для кожної позиції модель обирає хід у двох режимах: «самостійно» (усі дозволені ходи) та
«гібрид» (5 найкращих ходів рушія). Рахується: частка правильних відповідей з першої спроби,
кількість повторів, середня втрата в сантипішаках і час. Потрібен заповнений .env.
Кожна позиція – щонайменше 2 запити до моделі; для платного сервісу це коштує грошей.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import chess

from app.engine import Engine
from app.llm import llm, llm_move

OUT = Path(__file__).resolve().parent.parent / "docs" / "data"


def positions(n: int, seed: int = 2026) -> list[chess.Board]:
    """Відтворюваний набір: короткі випадково-розумні партії рушія."""
    rng, out = random.Random(seed), []
    while len(out) < n:
        b = chess.Board()
        for _ in range(rng.randint(6, 40)):
            if b.is_game_over():
                break
            res = Engine().search(b, 1, nodes=2000, multi=True)
            b.push(rng.choice(res.scores[:3])[0])
        if not b.is_game_over() and b.legal_moves.count() > 5:
            out.append(b)
    return out


def main() -> None:
    if not llm.ready:
        sys.exit("Заповніть .env: мовну модель не підключено.")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    report = {"модель": llm.config.model, "позицій": n}
    boards = positions(n)
    for mode, level in (("самостійно", 3), ("гібрид", 4)):
        first = fallback = 0
        losses, times, tries = [], [], []
        for i, b in enumerate(boards, 1):
            move, info = llm_move(b, level)
            first += info["attempts"] == 1 and not info["fallback"]
            fallback += info["fallback"]
            tries.append(info["attempts"])
            times.append(info["seconds"])
            if not info["fallback"]:
                best = Engine().search(b, 6, nodes=30_000, min_depth=2).score
                nb = b.copy()
                nb.push(move)
                got = -Engine().search(nb, 5, nodes=30_000, min_depth=2).score
                losses.append(max(0, min(1000, best) - max(-1000, min(1000, got))))
            print(f"{mode}: {i}/{n} {move.uci()} спроб {info['attempts']} {info['errors']}", flush=True)
        report[mode] = {
            "правильно_з_першої_спроби_%": round(100 * first / n, 1),
            "довелося_ходити_рушієм_%": round(100 * fallback / n, 1),
            "середня_кількість_спроб": round(sum(tries) / n, 2),
            "середня_втрата_сп": round(sum(losses) / len(losses)) if losses else None,
            "середній_час_с": round(sum(times) / n, 2),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    name = "".join(c if c.isalnum() else "_" for c in llm.config.model)
    path = OUT / f"llm_{name}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), "\nЗбережено:", path)


if __name__ == "__main__":
    main()
