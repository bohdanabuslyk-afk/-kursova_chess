"""Аналіз партії: оцінка кожної позиції, клас ходу, точність, пояснення за фактами."""
from __future__ import annotations

import math
import threading

import chess

from .engine import MATE, MATE_ZONE, VALUE_MG, Engine, SearchResult
from .openings import book_plies

PIECE = {chess.PAWN: "пішак", chess.KNIGHT: "кінь", chess.BISHOP: "слон", chess.ROOK: "тура", chess.QUEEN: "ферзь", chess.KING: "король"}
PIECE_ACC = {chess.PAWN: "пішака", chess.KNIGHT: "коня", chess.BISHOP: "слона", chess.ROOK: "туру", chess.QUEEN: "ферзя", chess.KING: "короля"}

# клас -> (назва, позначка)
CLASSES = {
    "book": ("теорія", "≡"),
    "best": ("найкращий", "★"),
    "good": ("хороший", "✓"),
    "inacc": ("неточність", "?!"),
    "mistake": ("помилка", "?"),
    "blunder": ("груба помилка", "??"),
    "forced": ("єдиний", "□"),
}
SPEEDS = {"fast": (5, 0.6), "deep": (8, 2.0)}  # глибина, секунд на позицію


def win_percent(cp: int) -> float:
    """Оцінка в сантипішаках -> шанси на перемогу, % (логістична крива)."""
    if abs(cp) >= MATE_ZONE:
        return 100.0 if cp > 0 else 0.0
    return 100 / (1 + math.exp(-0.00368208 * cp))


def move_accuracy(loss: float) -> float:
    """Втрата шансів (у відсоткових пунктах) -> точність ходу 0..100."""
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * loss) - 3.1669))


def classify(loss: float, is_best: bool, is_book: bool, only_move: bool) -> str:
    if only_move:
        return "forced"
    if is_book and loss < 10:
        return "book"
    if is_best or loss < 1:
        return "best"
    if loss < 5:
        return "good"
    if loss < 10:
        return "inacc"
    if loss < 20:
        return "mistake"
    return "blunder"


def score_text(white_cp: int) -> str:
    if abs(white_cp) >= MATE_ZONE:
        n = (MATE - abs(white_cp) + 1) // 2
        return ("+" if white_cp > 0 else "−") + f"М{n}" if n else ("1–0" if white_cp > 0 else "0–1")
    return f"{white_cp / 100:+.2f}".replace("-", "−")


class Analysis:
    """Рахується у фоновому потоці; стан можна читати в будь-який момент."""

    def __init__(self, board: chess.Board, speed: str = "fast") -> None:
        self.moves = list(board.move_stack)
        self.depth, self.seconds = SPEEDS[speed]
        self.speed = speed
        self.done = 0
        self.total = len(self.moves) + 1
        self.rows: list[dict] = []
        self.summary: dict | None = None
        self.error: str | None = None
        self.cancelled = False

    def start(self) -> None:
        threading.Thread(target=self._safe_run, daemon=True).start()

    def _safe_run(self) -> None:
        try:
            self.run()
        except Exception as e:  # помилку показуємо користувачу, а не лише в консолі
            self.error = f"Аналіз перервано: {e}"

    def run(self) -> None:
        engine = Engine()  # спільна таблиця транспозицій для всієї партії
        board = chess.Board()
        before = self._eval(engine, board)
        self.done = 1
        sans: list[str] = []
        for i, move in enumerate(self.moves):
            if self.cancelled:
                return
            only = board.legal_moves.count() == 1
            san = board.san(move)
            sans.append(san)
            color = board.turn
            board.push(move)
            after = self._eval(engine, board)
            board.pop()
            row = self._row(board, i, move, san, color, before, after, sans, only)
            board.push(move)
            self.rows.append(row)
            before = after
            self.done += 1
        self.summary = self._summary()

    def _eval(self, engine: Engine, board: chess.Board) -> SearchResult:
        if board.is_insufficient_material() or board.is_repetition(3) or board.halfmove_clock >= 100:
            return SearchResult(next(iter(board.legal_moves), None), 0)
        return engine.search(board, self.depth, self.seconds, min_depth=2)

    def _row(self, board, i, move, san, color, before, after, sans, only) -> dict:
        sign = 1 if color else -1
        best = before.move
        is_best = move == best
        played = -after.score
        win_before = win_percent(before.score)
        win_after = win_percent(played)
        loss = 0.0 if is_best or only else max(0.0, win_before - win_after)
        cp_loss = 0 if is_best or only else max(0, min(1000, before.score) - max(-1000, min(1000, played)))
        cls = classify(loss, is_best, i < book_plies(sans), only)
        row = {
            "ply": i + 1, "san": san, "uci": move.uci(), "color": "white" if color else "black",
            "score": max(-MATE, min(MATE, -sign * after.score)),
            "scoreText": score_text(-sign * after.score),
            "win": round(win_percent(-sign * after.score), 1),
            "best": board.san(best), "bestUci": best.uci(),
            "bestScoreText": score_text(sign * before.score),
            "bestLine": board.variation_san(before.pv[:6]) if before.pv else "",
            "replyLine": "", "loss": round(loss, 1), "cpLoss": min(1000, cp_loss), "accuracy": round(move_accuracy(loss), 1),
            "class": cls, "className": CLASSES[cls][0], "mark": CLASSES[cls][1], "depth": after.depth,
        }
        nb = board.copy()
        nb.push(move)
        if after.pv and after.move in nb.legal_moves:
            row["replyLine"] = nb.variation_san(after.pv[:6])
        row["facts"] = facts(board, move, row, best, after)
        return row

    def _summary(self) -> dict:
        out: dict = {}
        for color in ("white", "black"):
            rows = [r for r in self.rows if r["color"] == color]
            n = len(rows) or 1
            out[color] = {
                "moves": len(rows),
                "accuracy": round(sum(r["accuracy"] for r in rows) / n, 1) if rows else None,
                "acpl": round(sum(r["cpLoss"] for r in rows) / n) if rows else None,
                "counts": {c: sum(r["class"] == c for r in rows) for c in CLASSES},
            }
        worst = sorted((r for r in self.rows if r["loss"] >= 10), key=lambda r: -r["loss"])[:5]
        out["moments"] = sorted(r["ply"] for r in worst)
        return out

    def state(self) -> dict:
        return {
            "done": self.done, "total": self.total, "speed": self.speed, "error": self.error,
            "rows": list(self.rows), "summary": self.summary,
            "classes": {k: {"name": v[0], "mark": v[1]} for k, v in CLASSES.items()},
        }


def hanging(board: chess.Board, color: chess.Color) -> list[str]:
    """Фігури кольору color, які можна вигідно побити (дешевшою фігурою або без захисту)."""
    out = []
    for sq, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        attackers = board.attackers(not color, sq)
        if not attackers:
            continue
        cheapest = min(VALUE_MG[board.piece_type_at(a)] or 10_000 for a in attackers)
        if not board.attackers(color, sq) or cheapest + 60 < VALUE_MG[piece.piece_type]:
            out.append(f"{PIECE[piece.piece_type]} {chess.square_name(sq)}")
    return out


def facts(board: chess.Board, move: chess.Move, row: dict, best: chess.Move, after: SearchResult) -> list[str]:
    """Перевірені факти про хід. Вони ж ідуть у підказку для LLM, щоб вона не вигадувала."""
    out: list[str] = []
    piece = board.piece_type_at(move.from_square)
    nb = board.copy()
    nb.push(move)
    if nb.is_checkmate():
        return ["Мат – партію завершено."]
    if nb.is_stalemate():
        out.append("Пат – нічия.")
    if board.is_castling(move):
        out.append("Рокіровка: король сховався, тура ввійшла в гру.")
    if board.is_en_passant(move):
        out.append("Взяття на проході.")
    elif board.is_capture(move):
        out.append(f"{PIECE[piece].capitalize()} бере {PIECE_ACC[board.piece_type_at(move.to_square)]} на {chess.square_name(move.to_square)}.")
    if move.promotion:
        out.append(f"Пішак перетворюється на {PIECE_ACC[move.promotion]}.")
    if nb.is_check():
        out.append("Хід дає шах.")
    mine, theirs = hanging(nb, board.turn), hanging(nb, not board.turn)
    if mine:
        out.append("Під боєм без достатнього захисту: " + ", ".join(mine) + ".")
    if theirs and not nb.is_check():
        out.append("Хід нападає на: " + ", ".join(theirs) + ".")
    if after.mate_in is not None:
        if after.mate_in > 0:
            out.append(f"Тепер суперник може поставити мат у {after.mate_in} ход.")
        else:
            out.append(f"Далі є форсований мат у {-after.mate_in} ход.")
    if row["class"] in ("inacc", "mistake", "blunder"):
        out.append(f"Втрачено {row['loss']:.0f} в. п. шансів на перемогу.")
        out.append(f"Сильніше було {row['best']} ({row['bestScoreText']}): {row['bestLine']}.")
        if row["replyLine"]:
            out.append(f"Тепер найсильніша відповідь: {row['replyLine']}.")
    elif row["class"] == "good":
        out.append(f"Рушій трохи більше любить {row['best']}.")
    elif row["class"] == "book":
        out.append("Відомий теоретичний хід.")
    elif row["class"] == "forced":
        out.append("Це єдиний можливий хід.")
    elif row["class"] == "best":
        out.append("Один із найсильніших ходів у позиції.")
    return out
