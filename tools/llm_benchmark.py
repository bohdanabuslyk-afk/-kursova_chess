"""Вимірювання мовної моделі: python -m tools.llm_benchmark [позицій] [межа запитів]

Для кожної позиції модель обирає хід у двох режимах: «самостійно» (усі дозволені ходи) та
«гібрид» (5 найкращих ходів рушія). Потрібен заповнений .env.

Щоб дані були чесними:
  * збій сервісу (ліміт, перевантаження, мережа) не рахується помилкою моделі – позиція повторюється,
    а якщо не вдалося тричі, вилучається і показується окремо;
  * є точка відліку: середня втрата випадкового дозволеного ходу та випадкового ходу з тих самих п'яти;
  * загальна кількість запитів має жорстку межу (типово 120).
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

import chess
import openai

from app.engine import LEVELS, Engine
from app.llm import HYBRID, LLM, LLMError, llm_move

OUT = Path(__file__).resolve().parent.parent / "docs" / "data"
PAUSE = 5.0   # секунд між запитами
NODES = 30_000


class Budget(Exception):
    pass


class Counted(LLM):
    """Модель з лічильником запитів, паузами та без прихованих повторів SDK."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit, self.count, self.service_errors, self.last = limit, 0, 0, 0.0
        self.seconds: list[float] = []
        if self.ready:
            self._client = openai.OpenAI(base_url=self.config.base_url, api_key=self.config.api_key,
                                         timeout=self.config.timeout, max_retries=0)

    def ask(self, messages: list[dict]) -> str:
        if self.count >= self.limit:
            raise Budget
        time.sleep(max(0.0, self.last + PAUSE - time.time()))
        self.count += 1
        start = time.time()
        try:
            text = super().ask(messages)
        except LLMError:
            self.service_errors += 1
            raise
        finally:
            self.last = time.time()
        self.seconds.append(self.last - start)
        return text


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


class Judge:
    """Втрата ходу в сантипішаках відносно найкращого (0…1000+)."""

    def __init__(self) -> None:
        self.cache: dict = {}

    def value(self, board: chess.Board, move: chess.Move | None) -> int:
        key = (board.fen(), move)
        if key not in self.cache:
            b = board.copy()
            if move:
                b.push(move)
                score = 0 if b.is_stalemate() or b.is_insufficient_material() else -Engine().search(b, 5, nodes=NODES, min_depth=2).score
            else:
                score = Engine().search(b, 6, nodes=NODES, min_depth=2).score
            self.cache[key] = max(-1000, min(1000, score))
        return self.cache[key]

    def loss(self, board: chess.Board, move: chess.Move) -> int:
        return max(0, self.value(board, None) - self.value(board, move))


def mean(xs):
    return round(sum(xs) / len(xs), 2) if xs else None


def run_mode(model: Counted, judge: Judge, boards: list[chess.Board], level: int) -> list[dict]:
    rows = []
    for i, b in enumerate(boards, 1):
        row = {"fen": b.fen()}
        try:
            for attempt in range(3):
                errors_before, seconds_before = model.service_errors, len(model.seconds)
                move, info = llm_move(b, level, model)
                if model.service_errors == errors_before:
                    row.update(move=move.uci(), attempts=info["attempts"], fallback=info["fallback"], errors=info["errors"],
                               seconds=round(sum(model.seconds[seconds_before:]), 2))
                    break
                row["service_error"] = info["errors"][-1]
                print(f"  збій сервісу: {info['errors'][-1]}", flush=True)
                time.sleep(30)
            else:
                move = None
        except Budget:
            print("Досягнуто межі запитів", flush=True)
            break
        if "move" in row:
            row.pop("service_error", None)
            row["legal_first"] = row["attempts"] == 1 and not row["fallback"]
            row["loss"] = None if row["fallback"] else judge.loss(b, move)
        rows.append(row)
        print(f"рівень {level}: {i}/{len(boards)} {row.get('move')} спроб {row.get('attempts')} втрата {row.get('loss')}", flush=True)
    return rows


def baseline(judge: Judge, boards: list[chess.Board], level: int | None) -> float | None:
    """Середня втрата випадкового вибору: з усіх ходів (вибірка 5) або з ходів гібрида."""
    rng, out = random.Random(7), []
    for b in boards:
        if level is None:
            moves = list(b.legal_moves)
            moves = rng.sample(moves, min(5, len(moves)))
        else:
            res = Engine().search(b, LEVELS[level].depth, 2.0, multi=True)
            moves = [m for m, _ in res.scores[:HYBRID[level]]]
        out.append(sum(judge.loss(b, m) for m in moves) / len(moves))
    return mean(out)


def summary(rows: list[dict], base: float | None) -> dict:
    ok = [r for r in rows if "move" in r]
    losses = [r["loss"] for r in ok if r["loss"] is not None]
    n = len(ok) or 1
    return {
        "оцінено_позицій": len(ok),
        "вилучено_через_збій_сервісу": len(rows) - len(ok),
        "легально_з_першої_спроби": sum(r["legal_first"] for r in ok),
        "легально_з_першої_спроби_%": round(100 * sum(r["legal_first"] for r in ok) / n, 1),
        "довелося_ходити_рушієм": sum(r["fallback"] for r in ok),
        "середня_кількість_спроб": mean([r["attempts"] for r in ok]),
        "середня_втрата_сп": mean(losses),
        "медіана_втрати_сп": statistics.median(losses) if losses else None,
        "грубих_помилок_(втрата>=200)": sum(x >= 200 for x in losses),
        "для_порівняння_випадковий_хід_сп": base,
        "середній_час_відповіді_с": mean([r["seconds"] for r in ok]),
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    model = Counted(int(sys.argv[2]) if len(sys.argv) > 2 else 120)
    if not model.ready:
        sys.exit("Заповніть .env: мовну модель не підключено.")
    judge, boards = Judge(), positions(n)
    # спершу запити до моделі, потім довгі обчислення точки відліку
    raw = {"самостійно": run_mode(model, judge, boards, 3), "гібрид": run_mode(model, judge, boards, 4)}
    report = {
        "модель": model.config.model, "дата": time.strftime("%Y-%m-%d"), "позицій": n,
        "запитів_усього": model.count, "збоїв_сервісу": model.service_errors,
        "самостійно": summary(raw["самостійно"], baseline(judge, boards, None)),
        "гібрид": summary(raw["гібрид"], baseline(judge, boards, 4)),
        "подробиці": raw,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    name = "".join(c if c.isalnum() else "_" for c in model.config.model)
    path = OUT / f"llm_{name}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "подробиці"}, ensure_ascii=False, indent=2))
    print("Збережено:", path)


if __name__ == "__main__":
    main()
