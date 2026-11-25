"""Стан однієї партії. Усі правила перевіряє python-chess."""
from __future__ import annotations

import threading
import uuid

import chess


class MoveError(ValueError):
    """Хід не розпізнано або він порушує правила."""


REASONS = {
    chess.Termination.CHECKMATE: "мат",
    chess.Termination.STALEMATE: "пат",
    chess.Termination.INSUFFICIENT_MATERIAL: "недостатньо фігур для мату",
    chess.Termination.SEVENTYFIVE_MOVES: "правило 75 ходів",
    chess.Termination.FIVEFOLD_REPETITION: "п'ятикратне повторення",
    chess.Termination.FIFTY_MOVES: "правило 50 ходів",
    chess.Termination.THREEFOLD_REPETITION: "триразове повторення",
}


def parse_move(board: chess.Board, text: str) -> chess.Move:
    """Розпізнає хід: UCI (e2e4, e7e8q) або SAN (Nf3, O-O, exd5)."""
    text = (text or "").strip().replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    if not text:
        raise MoveError("Хід порожній")
    try:
        move = chess.Move.from_uci(text.lower().replace("-", "").replace(" ", ""))
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    try:
        move = board.parse_san(text)
        if move:  # parse_san приймає й «нульовий хід» (0000, --), у шахах його немає
            return move
    except chess.AmbiguousMoveError:
        raise MoveError(f"Хід «{text}» неоднозначний: уточніть фігуру") from None
    except ValueError:
        pass
    raise MoveError(f"Хід «{text}» неможливий у цій позиції")


class Game:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.board = chess.Board()
        self.lock = threading.RLock()

    def play(self, text: str) -> chess.Move:
        with self.lock:
            if self.outcome()[0]:
                raise MoveError("Партію вже завершено")
            move = parse_move(self.board, text)
            self.board.push(move)
            return move

    def outcome(self) -> tuple[str | None, str | None]:
        """(результат, причина) або (None, None), якщо партія триває."""
        out = self.board.outcome()
        if out:
            return out.result(), REASONS[out.termination]
        # claim_draw=True не підходить: він завершує партію на півхід раніше,
        # коли повторення лише можна заявити наступним ходом.
        if self.board.is_repetition(3):
            return "1/2-1/2", REASONS[chess.Termination.THREEFOLD_REPETITION]
        if self.board.halfmove_clock >= 100:
            return "1/2-1/2", REASONS[chess.Termination.FIFTY_MOVES]
        return None, None

    def history(self) -> list[dict]:
        board = chess.Board()
        rows = []
        for i, move in enumerate(self.board.move_stack):
            san = board.san(move)
            board.push(move)
            rows.append({
                "ply": i + 1,
                "san": san,
                "uci": move.uci(),
                "fen": board.fen(),
                "check": chess.square_name(board.king(board.turn)) if board.is_check() else None,
            })
        return rows

    def state(self) -> dict:
        with self.lock:
            result, reason = self.outcome()
            legal: dict[str, list[str]] = {}
            if not result:
                for m in self.board.legal_moves:
                    targets = legal.setdefault(chess.square_name(m.from_square), [])
                    to = chess.square_name(m.to_square)
                    if to not in targets:
                        targets.append(to)
            return {
                "id": self.id,
                "fen": self.board.fen(),
                "turn": "white" if self.board.turn else "black",
                "legal": legal,
                "history": self.history(),
                "result": result,
                "reason": reason,
            }
