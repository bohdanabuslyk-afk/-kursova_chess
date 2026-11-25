"""Стан однієї партії. Усі правила перевіряє python-chess."""
from __future__ import annotations

import datetime as dt
import io
import logging
import random
import re
import threading
import uuid

import chess
import chess.pgn

from .engine import LEVELS, choose_move
from .openings import opening_name


class MoveError(ValueError):
    """Хід не розпізнано, порушено правила або задано хибні налаштування."""


REASONS = {
    chess.Termination.CHECKMATE: "мат",
    chess.Termination.STALEMATE: "пат",
    chess.Termination.INSUFFICIENT_MATERIAL: "недостатньо фігур для мату",
    chess.Termination.SEVENTYFIVE_MOVES: "правило 75 ходів",
    chess.Termination.FIVEFOLD_REPETITION: "п'ятикратне повторення",
    chess.Termination.FIFTY_MOVES: "правило 50 ходів",
    chess.Termination.THREEFOLD_REPETITION: "триразове повторення",
}
logging.getLogger("chess.pgn").setLevel(logging.CRITICAL)  # помилки PGN показуємо самі
OPPONENTS = ("human", "engine", "llm")


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
        """color – колір гравця; opponent: human (двоє за одним екраном), engine або llm."""
        if color == "random":
            color = random.choice(("white", "black"))
        if color not in ("white", "black"):
            raise MoveError("Невідомий колір")
        if opponent not in OPPONENTS:
            raise MoveError("Невідомий суперник")
        if not isinstance(level, int) or level not in LEVELS:
            raise MoveError("Невідомий рівень складності")
        self.id = uuid.uuid4().hex[:12]
        self.color, self.opponent, self.level = color, opponent, level
        self.board = chess.Board()
        self.lock = threading.RLock()
        self.info: dict | None = None  # дані про останній хід суперника
        self.resigned: str | None = None  # колір, що здався
        self.imported = False
        self.created = dt.datetime.now()
        self.analysis = None
        self.chat: list[dict] = []

    # ---------- ходи ----------
    @property
    def players_turn(self) -> bool:
        return self.opponent == "human" or self.board.turn == (self.color == "white")

    def _check_active(self) -> None:
        if self.imported:
            raise MoveError("Імпортовану партію можна лише переглядати")
        if self.outcome()[0]:
            raise MoveError("Партію вже завершено")

    def play(self, text: str) -> chess.Move:
        with self.lock:
            self._check_active()
            if not self.players_turn:
                raise MoveError("Зараз хід суперника")
            move = parse_move(self.board, text)
            self._push(move)
            return move

    def _drop_analysis(self) -> None:
        if self.analysis:
            self.analysis.cancelled = True
        self.analysis = None

    def _push(self, move: chess.Move) -> None:
        self.board.push(move)
        self._drop_analysis()

    def reply(self) -> None:
        """Хід комп'ютера. Пошук іде на копії дошки, тому стан можна читати паралельно."""
        with self.lock:
            if self.imported or self.outcome()[0] or self.players_turn:
                return
            board, fen = self.board.copy(), self.board.fen()
        move, info = self._think(board)
        with self.lock:
            # Поки суперник думав, гравець міг скасувати хід або здатися.
            if self.board.fen() != fen or self.outcome()[0]:
                return
            self.info = info
            self._push(move)

    def _think(self, board: chess.Board) -> tuple[chess.Move, dict]:
        res = choose_move(board, self.level)
        return res.move, {
            "by": "engine", "depth": res.depth, "nodes": res.nodes, "seconds": round(res.seconds, 2),
            "pv": board.variation_san(res.pv) if res.pv else "",
        }

    def undo(self) -> None:
        """Скасовує останній хід гравця (разом із відповіддю суперника)."""
        with self.lock:
            if self.imported:
                raise MoveError("Імпортовану партію можна лише переглядати")
            if self.resigned:
                self.resigned = None
                return
            mine = chess.WHITE if self.color == "white" else chess.BLACK
            stack = self.board.move_stack
            has_mine = self.opponent == "human" or any((i % 2 == 0) == mine for i in range(len(stack)))
            if not stack or not has_mine:
                raise MoveError("Немає ходів для скасування")
            self.board.pop()
            while self.opponent != "human" and self.board.turn != mine:
                self.board.pop()
            self.info = None
            self._drop_analysis()

    def resign(self) -> None:
        with self.lock:
            self._check_active()
            self.resigned = self.color if self.opponent != "human" else ("white" if self.board.turn else "black")

    def outcome(self) -> tuple[str | None, str | None]:
        """(результат, причина) або (None, None), якщо партія триває."""
        if self.resigned:
            who = "білі здалися" if self.resigned == "white" else "чорні здалися"
            return ("0-1" if self.resigned == "white" else "1-0"), who
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

    # ---------- подання ----------
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
            if not result and self.players_turn and not self.imported:
                for m in self.board.legal_moves:
                    targets = legal.setdefault(chess.square_name(m.from_square), [])
                    to = chess.square_name(m.to_square)
                    if to not in targets:
                        targets.append(to)
            rows = self.history()
            return {
                "id": self.id,
                "color": self.color,
                "opponent": self.opponent,
                "level": self.level,
                "levelName": LEVELS[self.level].name,
                "playersTurn": self.players_turn or self.imported,
                "imported": self.imported,
                "info": self.info,
                "fen": self.board.fen(),
                "startFen": chess.STARTING_FEN,
                "turn": "white" if self.board.turn else "black",
                "legal": legal,
                "history": rows,
                "opening": opening_name([r["san"] for r in rows]),
                "result": result,
                "reason": reason,
            }

    # ---------- PGN ----------
    def names(self) -> tuple[str, str]:
        level = LEVELS[self.level].name
        bot = {"engine": f"Рушій ({level})", "llm": f"LLM ({level})", "human": "Гравець 2"}[self.opponent]
        return ("Гравець", bot) if self.color == "white" else (bot, "Гравець")

    def pgn(self) -> str:
        with self.lock:
            game = chess.pgn.Game.from_board(self.board)
            white, black = self.names()
            result, reason = self.outcome()
            game.headers.update({
                "Event": "Шахова гра з LLM", "Site": "localhost", "Date": self.created.strftime("%Y.%m.%d"),
                "Round": "-", "White": white, "Black": black, "Result": result or "*",
                "PlayerColor": self.color, "Opponent": self.opponent, "Level": str(self.level),
            })
            if reason:
                game.headers["Termination"] = reason
            if self.resigned:
                game.headers["Resigned"] = self.resigned
            return str(game)

    @classmethod
    def from_pgn(cls, text: str, imported: bool = True) -> "Game":
        parsed = chess.pgn.read_game(io.StringIO(text))
        if parsed is None or (parsed.next() is None and not re.search(r"^\[\w+ ", text, re.M)):
            raise MoveError("У тексті немає партії у форматі PGN")
        if parsed.errors:
            raise MoveError("PGN містить помилку: " + str(parsed.errors[0]))
        if parsed.board().fen() != chess.STARTING_FEN:
            raise MoveError("Підтримуються лише партії з початкової позиції")
        h = parsed.headers
        color, opponent, level = h.get("PlayerColor", "white"), h.get("Opponent", "human"), h.get("Level", "3")
        game = cls(color if color in ("white", "black") else "white",
                   opponent if opponent in OPPONENTS else "human",
                   int(level) if level in {str(i) for i in LEVELS} else 3)
        game.board = parsed.end().board()
        game.resigned = h.get("Resigned") if h.get("Resigned") in ("white", "black") else None
        game.imported = imported
        return game
