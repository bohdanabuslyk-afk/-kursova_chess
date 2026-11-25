"""Стан однієї партії. Усі правила перевіряє python-chess."""
from __future__ import annotations

import random
import threading
import uuid

import chess

from .engine import LEVELS, choose_move


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
    def __init__(self, color: str = "white", opponent: str = "human", level: int = 3) -> None:
        """color – колір гравця; opponent: human (двоє за одним екраном) або engine."""
        if color == "random":
            color = random.choice(("white", "black"))
        if color not in ("white", "black"):
            raise MoveError("Невідомий колір")
        if opponent not in ("human", "engine"):
            raise MoveError("Невідомий суперник")
        if level not in LEVELS:
            raise MoveError("Невідомий рівень складності")
        self.id = uuid.uuid4().hex[:12]
        self.color, self.opponent, self.level = color, opponent, level
        self.board = chess.Board()
        self.lock = threading.RLock()
        self.info: dict | None = None  # дані про останній хід суперника

    @property
    def players_turn(self) -> bool:
        return self.opponent == "human" or self.board.turn == (self.color == "white")

    def play(self, text: str) -> chess.Move:
        with self.lock:
            if self.outcome()[0]:
                raise MoveError("Партію вже завершено")
            if not self.players_turn:
                raise MoveError("Зараз хід суперника")
            move = parse_move(self.board, text)
            self.board.push(move)
            return move

    def reply(self) -> None:
        """Хід комп'ютера. Пошук іде на копії дошки, тому стан можна читати паралельно."""
        with self.lock:
            if self.outcome()[0] or self.players_turn:
                return
            board, fen = self.board.copy(), self.board.fen()
        res = choose_move(board, self.level)
        with self.lock:
            if self.board.fen() != fen:  # поки думали, стан партії змінився
                return
            self.info = {"depth": res.depth, "nodes": res.nodes, "seconds": round(res.seconds, 2),
                         "pv": board.variation_san(res.pv) if res.pv else ""}
            self.board.push(res.move)

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
            if not result and self.players_turn:
                for m in self.board.legal_moves:
                    targets = legal.setdefault(chess.square_name(m.from_square), [])
                    to = chess.square_name(m.to_square)
                    if to not in targets:
                        targets.append(to)
            return {
                "id": self.id,
                "color": self.color,
                "opponent": self.opponent,
                "level": self.level,
                "levelName": LEVELS[self.level].name,
                "playersTurn": self.players_turn,
                "info": self.info,
                "fen": self.board.fen(),
                "turn": "white" if self.board.turn else "black",
                "legal": legal,
                "history": self.history(),
                "result": result,
                "reason": reason,
            }
