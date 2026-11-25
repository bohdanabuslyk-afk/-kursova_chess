"""Мовна модель: суперник, пояснення ходів, тренер.

Головний принцип: відповідь моделі – лише пропозиція. Хід проходить перевірку правилами,
а пояснення будується на фактах, які порахував рушій.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import chess
import openai
from dotenv import load_dotenv

from .engine import LEVELS, Engine, choose_move

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "llm_log.jsonl"
load_dotenv(ROOT / ".env")


class LLMError(RuntimeError):
    """Зрозуміле для користувача повідомлення про збій моделі."""


@dataclass
class Config:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "Config":
        # Власні імена змінних: застосунок не підхопить чужий ключ із системи.
        try:
            timeout = float(os.getenv("CHESS_LLM_TIMEOUT") or 60)
        except ValueError:
            timeout = 60.0
        return cls(os.getenv("CHESS_LLM_BASE_URL", "").strip(), os.getenv("CHESS_LLM_API_KEY", "").strip(),
                   os.getenv("CHESS_LLM_MODEL", "").strip(), timeout)

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


class LLM:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.from_env()
        self._client = None

    @property
    def ready(self) -> bool:
        return self.config.ready

    def status(self) -> dict:
        # Ключ навмисно не повертається: у браузер він не потрапляє.
        return {"ready": self.ready, "model": self.config.model if self.ready else None}

    def ask(self, messages: list[dict]) -> str:
        if not self.ready:
            raise LLMError("Мовну модель не підключено: заповніть файл .env")
        if self._client is None:
            self._client = openai.OpenAI(base_url=self.config.base_url, api_key=self.config.api_key,
                                         timeout=self.config.timeout, max_retries=1)
        try:
            r = self._client.chat.completions.create(model=self.config.model, messages=messages)
        except openai.AuthenticationError:
            raise LLMError("Сервіс відхилив ключ API") from None
        except openai.NotFoundError:
            raise LLMError(f"Модель «{self.config.model}» або адресу сервісу не знайдено") from None
        except openai.RateLimitError:
            raise LLMError("Перевищено ліміт запитів або закінчився баланс") from None
        except openai.APITimeoutError:
            raise LLMError("Модель не відповіла вчасно") from None
        except openai.APIConnectionError:
            raise LLMError("Немає зв'язку із сервісом моделі") from None
        except openai.APIError as e:
            raise LLMError(f"Помилка сервісу моделі ({getattr(e, 'status_code', '?')})") from None
        text = (r.choices[0].message.content or "") if r.choices else ""
        # Деякі відкриті моделі друкують роздуми в тегах <think>.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        if not text:
            raise LLMError("Модель повернула порожню відповідь")
        return text


llm = LLM()


def extract_json(text: str) -> dict | None:
    """Дістає перший JSON-об'єкт із відповіді, навіть якщо навколо є текст чи ```."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            data, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def log(event: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **event}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- суперник
MAX_TRIES = 3
HYBRID = {4: 5, 5: 3}  # рівень -> зі скількох найкращих ходів рушія модель обирає

PERSONA = {
    1: "Ти граєш як новачок: обираєш прості природні ходи, інколи неточні.",
    2: "Ти граєш як любитель: розвиваєш фігури, бачиш прості взяття.",
    3: "Ти граєш уважно: перевіряєш, чи не залишаєш фігури під боєм.",
    4: "Ти граєш як сильний шахіст: обираєш найкращий план із запропонованих.",
    5: "Ти граєш як майстер: обираєш найсильніший хід із запропонованих.",
}


def history_text(board: chess.Board) -> str:
    root = board.root()
    return root.variation_san(board.move_stack) if board.move_stack else "(ходів ще не було)"


def move_messages(board: chess.Board, level: int, allowed: list[chess.Move]) -> list[dict]:
    side = "білими" if board.turn else "чорними"
    legal = ", ".join(f"{board.san(m)} ({m.uci()})" for m in allowed)
    return [
        {"role": "system", "content":
            f"Ти – суперник у шаховій партії, граєш {side}. {PERSONA[level]} "
            "Обери рівно один хід ЛИШЕ зі списку дозволених. "
            'Відповідай тільки JSON: {"move": "<хід у форматі UCI>", "comment": "<одне коротке речення українською про свій задум>"}'},
        {"role": "user", "content":
            f"Партія: {history_text(board)}\nFEN: {board.fen()}\nДошка (великі літери – білі):\n{board}\n"
            f"Дозволені ходи: {legal}"},
    ]


def read_move(board: chess.Board, text: str, allowed: list[chess.Move]) -> tuple[chess.Move | None, str, str]:
    """(хід або None, коментар, причина відмови)."""
    data = extract_json(text)
    if data is None:
        return None, "", "відповідь не є JSON"
    raw = str(data.get("move", "")).strip()
    comment = str(data.get("comment", "")).strip()[:300]
    move = None
    try:
        move = chess.Move.from_uci(raw.lower())
    except ValueError:
        try:
            move = board.parse_san(raw)
        except ValueError:
            return None, comment, f"«{raw[:20]}» – не хід або він неможливий"
    if move not in board.legal_moves:
        return None, comment, f"«{raw[:20]}» – нелегальний хід"
    if move not in allowed:
        return None, comment, f"«{raw[:20]}» – ходу немає серед запропонованих"
    return move, comment, ""


def llm_move(board: chess.Board, level: int, model: LLM | None = None) -> tuple[chess.Move, dict]:
    """Хід мовної моделі. Якщо вона тричі помилилася або недоступна – ходить рушій."""
    model = model or llm
    start = time.perf_counter()
    allowed = list(board.legal_moves)
    if level in HYBRID and len(allowed) > HYBRID[level]:
        res = Engine().search(board, LEVELS[level].depth, 2.0, multi=True)
        if res.scores:
            allowed = [m for m, _ in res.scores[:HYBRID[level]]]
    messages = move_messages(board, level, allowed)
    errors: list[str] = []
    move, comment = None, ""
    while move is None and len(errors) < MAX_TRIES:
        try:
            text = model.ask(messages)
        except LLMError as e:
            errors.append(str(e))
            break
        move, comment, why = read_move(board, text, allowed)
        if move is None:
            errors.append(why)
            messages += [{"role": "assistant", "content": text[:500]},
                         {"role": "user", "content": f"Хід не прийнято: {why}. Обери інший хід зі списку дозволених. Лише JSON."}]
    fallback = move is None
    if fallback:
        move, comment = choose_move(board, min(level, 3)).move, ""
    info = {
        "by": "engine" if fallback else "llm", "llm": True, "model": model.config.model, "fallback": fallback,
        "attempts": len(errors) + (not fallback), "errors": errors, "comment": comment,
        "mode": "гібрид" if level in HYBRID else "самостійно", "seconds": round(time.perf_counter() - start, 2),
    }
    log({"event": "move", "level": level, "fen": board.fen(), "move": move.uci(), **info})
    return move, info


# ---------------------------------------------------------------- пояснення
COACH = ("Ти – доброзичливий шаховий тренер. Пишеш українською, просто й коротко, без розмітки Markdown. "
         "Спирайся ЛИШЕ на наведені дані рушія: не вигадуй ходів, варіантів та оцінок, яких там немає.")


def explain_messages(board: chess.Board, row: dict) -> list[dict]:
    who = "білі" if row["color"] == "white" else "чорні"
    lines = [f"Позиція перед ходом (FEN): {board.fen()}", f"Зіграли {who}: {row['san']}. Оцінка рушія: {row['className']}.",
             f"Оцінка після ходу (за білих): {row['scoreText']}."]
    if row["uci"] != row["bestUci"]:
        lines.append(f"Найкращий хід за рушієм: {row['best']} ({row['bestScoreText']}), варіант: {row['bestLine']}.")
    lines += [f"Факт: {f}" for f in row["facts"]]
    return [{"role": "system", "content": COACH},
            {"role": "user", "content": "\n".join(lines) + "\n\nПоясни учневі цей хід за 2–4 речення: ідея ходу, що сталося на дошці, на що звернути увагу."}]


def suspicious_moves(text: str, allowed_text: str) -> list[str]:
    """Ходи у тексті моделі, яких немає в наданих їй даних, – імовірна вигадка."""
    pattern = r"(?<![\w-])(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8])(?:=[QRBN])?"
    known = set(re.findall(pattern, allowed_text))
    return sorted(set(re.findall(pattern, text)) - known)


def explain(board: chess.Board, row: dict, model: LLM | None = None) -> dict:
    """Пояснення ходу: моделлю, а якщо вона недоступна – шаблоном із фактів."""
    model = model or llm
    template = " ".join(row["facts"]) or "Спокійний хід без прямих загроз."
    if not model.ready:
        return {"text": template, "by": "template", "warning": None}
    messages = explain_messages(board, row)
    try:
        text = model.ask(messages)
    except LLMError as e:
        return {"text": template, "by": "template", "warning": str(e)}
    extra = suspicious_moves(text, messages[1]["content"])
    warning = f"Модель згадала ходи, яких не було в даних рушія: {', '.join(extra)}. Перевірте їх." if extra else None
    log({"event": "explain", "move": row["san"], "model": model.config.model, "suspicious": extra})
    return {"text": text, "by": "llm", "model": model.config.model, "warning": warning}


def chat(board: chess.Board, history: list[dict], question: str, model: LLM | None = None) -> str:
    """Відповідь тренера на запитання про поточну позицію."""
    model = model or llm
    if not model.ready:
        raise LLMError("Мовну модель не підключено: заповніть файл .env")
    facts = f"Партія: {history_text(board)}\nFEN: {board.fen()}\nДошка (великі літери – білі):\n{board}\n"
    if not board.is_game_over():
        res = Engine().search(board, 6, 1.5)
        facts += (f"Хід {'білих' if board.turn else 'чорних'}. Рушій радить {board.san(res.move)}, "
                  f"варіант {board.variation_san(res.pv)}, оцінка за білих {(res.score if board.turn else -res.score) / 100:+.2f}.")
    messages = [{"role": "system", "content": COACH + " Якщо питання не про шахи, ввічливо поверни розмову до партії."}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-8:]]
    messages.append({"role": "user", "content": f"Дані про позицію:\n{facts}\n\nЗапитання учня: {question}"})
    return model.ask(messages)
