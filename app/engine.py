"""Шаховий рушій: мінімакс з альфа-бета відсіканням (форма негамакс).

Складові:
  * оцінка позиції – матеріал + таблиці «фігура-поле», плавний перехід мітельшпіль/ендшпіль;
  * ітеративне заглиблення з обмеженням часу;
  * таблиця транспозицій (ключ – бітборди позиції, їх не треба хешувати заново);
  * впорядкування ходів: хід з таблиці, взяття MVV-LVA, «вбивці», історія;
  * пошук спокою (quiescence) – прораховує взяття, щоб не обірвати розмін посередині.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import chess

MATE = 100_000
MATE_ZONE = MATE - 1_000

VALUE_MG = {chess.PAWN: 82, chess.KNIGHT: 337, chess.BISHOP: 365, chess.ROOK: 477, chess.QUEEN: 1025, chess.KING: 0}
VALUE_EG = {chess.PAWN: 94, chess.KNIGHT: 281, chess.BISHOP: 297, chess.ROOK: 512, chess.QUEEN: 936, chess.KING: 0}
PHASE = {chess.PAWN: 0, chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4, chess.KING: 0}

# Таблиці записані так, як дошку бачать білі: перший рядок – 8-ма горизонталь.
_PAWN_MG = [
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 27, 27, 10, 5, 5,
    0, 0, 5, 25, 25, 0, 0, 0,
    5, -5, -10, 2, 2, -10, -5, 5,
    5, 10, 10, -24, -24, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0]
_PAWN_EG = [
    0, 0, 0, 0, 0, 0, 0, 0,
    120, 120, 120, 120, 120, 120, 120, 120,
    70, 70, 65, 60, 60, 65, 70, 70,
    35, 30, 25, 20, 20, 25, 30, 35,
    15, 12, 5, 2, 2, 5, 12, 15,
    5, 6, 0, 4, 4, 0, 6, 5,
    8, 6, 6, 8, 8, 6, 6, 8,
    0, 0, 0, 0, 0, 0, 0, 0]
_KNIGHT = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50]
_BISHOP = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 8, 0, 0, 0, 0, 8, -10,
    -20, -10, -12, -10, -10, -12, -10, -20]
_ROOK = [
    0, 0, 0, 0, 0, 0, 0, 0,
    8, 12, 12, 12, 12, 12, 12, 8,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 2, 6, 6, 4, 0, 0]
_QUEEN = [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20]
_KING_MG = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20]
_KING_EG = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50]

_PST_MG = {chess.PAWN: _PAWN_MG, chess.KNIGHT: _KNIGHT, chess.BISHOP: _BISHOP, chess.ROOK: _ROOK, chess.QUEEN: _QUEEN, chess.KING: _KING_MG}
_PST_EG = {chess.PAWN: _PAWN_EG, chess.KNIGHT: _KNIGHT, chess.BISHOP: _BISHOP, chess.ROOK: _ROOK, chess.QUEEN: _QUEEN, chess.KING: _KING_EG}

# Готові суми «матеріал + поле»: TABLE[колір][тип] = [(mg, eg) для 64 полів]
TABLE = {
    color: {
        pt: [(VALUE_MG[pt] + _PST_MG[pt][sq ^ 56 if color else sq],
              VALUE_EG[pt] + _PST_EG[pt][sq ^ 56 if color else sq]) for sq in range(64)]
        for pt in chess.PIECE_TYPES
    }
    for color in (chess.WHITE, chess.BLACK)
}


def evaluate(board: chess.Board) -> int:
    """Оцінка в сантипішаках з погляду сторони, що ходить."""
    mg = eg = phase = 0
    for color, sign in ((chess.WHITE, 1), (chess.BLACK, -1)):
        tables = TABLE[color]
        for pt in chess.PIECE_TYPES:
            table, weight = tables[pt], PHASE[pt]
            for sq in chess.scan_forward(board.pieces_mask(pt, color)):
                m, e = table[sq]
                mg += sign * m
                eg += sign * e
                phase += weight
        if board.pieces_mask(chess.BISHOP, color).bit_count() >= 2:
            mg += sign * 25
            eg += sign * 35
    phase = min(phase, 24)
    score = int((mg * phase + eg * (24 - phase)) / 24)  # int(), бо // округлює від'ємні вниз
    return score if board.turn else -score


@dataclass(frozen=True)
class Level:
    name: str
    depth: int          # найбільша глибина
    seconds: float      # обмеження часу
    blunder: float      # імовірність випадкового ходу
    noise: int          # розкид оцінки кореневих ходів, сантипішаки
    description: str


LEVELS = {
    1: Level("Новачок", 1, 0.5, 0.35, 120, "часто помиляється, бачить лише один хід"),
    2: Level("Легкий", 1, 1.0, 0.10, 60, "бачить прості взяття, інколи зіває"),
    3: Level("Середній", 2, 2.0, 0.0, 25, "рахує на 2 півходи, без грубих зівків"),
    4: Level("Складний", 4, 2.5, 0.0, 0, "рахує до 4 півходів"),
    5: Level("Експерт", 12, 5.0, 0.0, 0, "думає до 5 секунд, зазвичай 5–7 півходів"),
}


class _Timeout(Exception):
    pass


@dataclass
class SearchResult:
    move: chess.Move | None
    score: int                       # з погляду сторони, що ходить
    depth: int = 0
    nodes: int = 0
    seconds: float = 0.0
    pv: list[chess.Move] = field(default_factory=list)
    scores: list[tuple[chess.Move, int]] = field(default_factory=list)  # кореневі ходи (multi)

    @property
    def mate_in(self) -> int | None:
        """Мат через n ходів (від'ємне – мат нам) або None."""
        if abs(self.score) < MATE_ZONE:
            return None
        n = (MATE - abs(self.score) + 1) // 2
        return n if self.score > 0 else -n


EXACT, LOWER, UPPER = 0, 1, 2


class Engine:
    def __init__(self) -> None:
        self.tt: dict[tuple, tuple[int, int, int, chess.Move | None]] = {}
        self.evals: dict[tuple, int] = {}
        self._reset()

    def _reset(self) -> None:
        self.nodes = 0
        self.killers: dict[int, list[chess.Move]] = {}
        self.hist: dict[tuple[bool, int, int], int] = {}
        self.deadline = float("inf")
        self.node_limit = float("inf")
        self.path: set[tuple] = set()  # позиції партії та поточної гілки – для виявлення повторень

    def _eval(self, board: chess.Board) -> int:
        key = (board.pawns, board.knights, board.bishops, board.rooks, board.queens, board.kings,
               board.occupied_co[True], board.turn)
        score = self.evals.get(key)
        if score is None:
            if len(self.evals) > 300_000:
                self.evals.clear()
            score = self.evals[key] = evaluate(board)
        return score

    # ---------- впорядкування ----------
    @staticmethod
    def _capture_score(board: chess.Board, move: chess.Move) -> int:
        victim = board.piece_type_at(move.to_square) or chess.PAWN
        attacker = board.piece_type_at(move.from_square)
        return VALUE_MG[victim] * 10 - VALUE_MG[attacker] + (900 if move.promotion else 0)

    def _ordered(self, board: chess.Board, ply: int, tt_move: chess.Move | None) -> list[chess.Move]:
        killers = self.killers.get(ply, ())

        def key(m: chess.Move) -> int:
            if m == tt_move:
                return 10_000_000
            if board.is_capture(m):
                return 1_000_000 + self._capture_score(board, m)
            if m.promotion:
                return 900_000 + VALUE_MG[m.promotion]
            if m in killers:
                return 800_000
            return self.hist.get((board.turn, m.from_square, m.to_square), 0)

        return sorted(board.legal_moves, key=key, reverse=True)

    # ---------- пошук ----------
    def _tick(self) -> None:
        self.nodes += 1
        if self.nodes > self.node_limit or (not self.nodes & 255 and time.perf_counter() > self.deadline):
            raise _Timeout

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        self._tick()
        if board.is_check():  # під шахом розглядаємо всі відповіді
            best = -MATE + ply
            moves = self._ordered(board, ply, None)
            if not moves:
                return best
            if ply > 40:
                return self._eval(board)
            stand = None
        else:
            stand = best = self._eval(board)
            if best >= beta:
                return best
            alpha = max(alpha, best)
            moves = [m for m in board.generate_legal_captures()]
            moves += [m for m in board.generate_legal_moves(board.pawns, chess.BB_RANK_1 | chess.BB_RANK_8)
                      if m.promotion == chess.QUEEN and not board.is_capture(m)]
            moves.sort(key=lambda m: self._capture_score(board, m), reverse=True)
        for move in moves:
            if stand is not None and not move.promotion:
                victim = board.piece_type_at(move.to_square) or chess.PAWN
                if stand + VALUE_EG[victim] + 200 < alpha:  # дельта-відсікання
                    continue
                # Дорожчою фігурою беремо захищену дешевшу – майже завжди втрата.
                if VALUE_MG[board.piece_type_at(move.from_square)] > VALUE_MG[victim] + 60 \
                        and board.attackers_mask(not board.turn, move.to_square) \
                        and not board.is_en_passant(move):
                    continue
            board.push(move)
            try:
                score = -self._quiesce(board, -beta, -alpha, ply + 1)
            finally:
                board.pop()
            if score > best:
                best = score
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        return best

    def _search(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int, null_ok: bool = True) -> int:
        self._tick()
        key = board._transposition_key()
        if key in self.path or board.halfmove_clock >= 100 \
                or (board.occupied.bit_count() <= 4 and board.is_insufficient_material()):
            return 0
        in_check = board.is_check()
        if in_check:
            depth += 1  # подовження під шахом
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)

        self.path.add(key)
        try:
            return self._node(board, key, depth, alpha, beta, ply, null_ok, in_check)
        finally:
            self.path.discard(key)

    def _node(self, board: chess.Board, key: tuple, depth: int, alpha: int, beta: int, ply: int,
              null_ok: bool, in_check: bool) -> int:
        entry = self.tt.get(key)
        tt_move = None
        if entry:
            e_depth, e_flag, e_score, tt_move = entry
            if e_score >= MATE_ZONE:
                e_score -= ply
            elif e_score <= -MATE_ZONE:
                e_score += ply
            if e_depth >= depth and (e_flag == EXACT or (e_flag == LOWER and e_score >= beta)
                                     or (e_flag == UPPER and e_score <= alpha)):
                return e_score

        # Нульовий хід: якщо навіть пропустивши хід ми стоїмо краще за beta – відсікаємо.
        if null_ok and not in_check and depth >= 3 and beta < MATE_ZONE \
                and board.occupied_co[board.turn] & ~(board.pawns | board.kings):
            board.push(chess.Move.null())
            try:
                score = -self._search(board, depth - 3, -beta, -beta + 1, ply + 1, False)
            finally:
                board.pop()
            if score >= beta:
                return beta

        best, best_move, alpha0 = -MATE * 2, None, alpha
        moves = self._ordered(board, ply, tt_move)
        if not moves:
            return -MATE + ply if in_check else 0
        for i, move in enumerate(moves):
            quiet = not board.is_capture(move) and not move.promotion
            board.push(move)
            try:
                if i == 0:
                    score = -self._search(board, depth - 1, -beta, -alpha, ply + 1)
                else:  # пошук з нульовим вікном, за потреби – повторний
                    cut = 1 if quiet and i >= 4 and depth >= 3 and not in_check else 0
                    score = -self._search(board, depth - 1 - cut, -alpha - 1, -alpha, ply + 1)
                    if score > alpha and (cut or score < beta):
                        score = -self._search(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.pop()
            if score > best:
                best, best_move = score, move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if quiet:
                    k = self.killers.setdefault(ply, [])
                    if move not in k:
                        self.killers[ply] = [move] + k[:1]
                    h = (board.turn, move.from_square, move.to_square)
                    self.hist[h] = min(self.hist.get(h, 0) + depth * depth, 700_000)
                break

        stored = best + ply if best >= MATE_ZONE else best - ply if best <= -MATE_ZONE else best
        flag = UPPER if best <= alpha0 else LOWER if best >= beta else EXACT
        if len(self.tt) > 400_000:
            self.tt.clear()
        self.tt[key] = (depth, flag, stored, best_move)
        return best

    def _pv(self, board: chess.Board, first: chess.Move, limit: int) -> list[chess.Move]:
        line, b = [first], board.copy()
        b.push(first)
        while len(line) < limit and not b.is_game_over():
            entry = self.tt.get(b._transposition_key())
            if not entry or entry[3] is None or entry[3] not in b.legal_moves or b.is_repetition(2):
                break
            line.append(entry[3])
            b.push(entry[3])
        return line

    def search(self, board: chess.Board, depth: int = 4, seconds: float = 2.0, multi: bool = False,
               min_depth: int = 1, nodes: int | None = None) -> SearchResult:
        """Ітеративне заглиблення. multi=True – точна оцінка кожного кореневого ходу.
        Глибини до min_depth завершуються навіть тоді, коли ліміт вичерпано.
        nodes – ліміт позицій замість часу: результат однаковий на будь-якому комп'ютері."""
        if nodes is not None:
            seconds = float("inf")
        board = board.copy()
        self._reset()
        start = time.perf_counter()
        back = board.copy()
        self.path.add(back._transposition_key())
        while back.move_stack and back.halfmove_clock:  # старіші за незворотний хід не повторяться
            back.pop()
            self.path.add(back._transposition_key())
        moves = self._ordered(board, 0, None)
        if not moves:
            return SearchResult(None, -MATE if board.is_check() else 0)
        result = SearchResult(moves[0], evaluate(board), pv=[moves[0]])
        for d in range(1, depth + 1):
            free = d <= min_depth
            self.deadline = float("inf") if free else start + seconds
            self.node_limit = float("inf") if free or nodes is None else nodes
            alpha, scored = -MATE * 2, []
            try:
                for i, move in enumerate(moves):
                    board.push(move)
                    try:
                        if multi or i == 0:
                            score = -self._search(board, d - 1, -MATE * 2, MATE * 2 if multi else -alpha, 1)
                        else:
                            score = -self._search(board, d - 1, -alpha - 1, -alpha, 1)
                            if score > alpha:
                                score = -self._search(board, d - 1, -MATE * 2, -alpha, 1)
                    finally:
                        board.pop()
                    scored.append((move, score))
                    alpha = max(alpha, score)
            except _Timeout:
                break
            scored.sort(key=lambda t: t[1], reverse=True)
            moves = [m for m, _ in scored]
            result = SearchResult(moves[0], scored[0][1], d, pv=self._pv(board, moves[0], max(d, 6)),
                                  scores=scored if multi else [])
            if abs(result.score) >= MATE_ZONE and MATE - abs(result.score) <= d:
                break
            if d >= min_depth and (time.perf_counter() - start > seconds * 0.6
                                   or (nodes is not None and self.nodes > nodes * 0.6)):
                break
        result.nodes = self.nodes
        result.seconds = time.perf_counter() - start
        return result


def choose_move(board: chess.Board, level: int, rng: random.Random | None = None) -> SearchResult:
    """Хід суперника заданого рівня складності."""
    rng = rng or random.Random()
    lv = LEVELS[level]
    if lv.blunder and rng.random() < lv.blunder:
        return SearchResult(rng.choice(list(board.legal_moves)), 0)
    engine = Engine()
    if not lv.noise:
        return engine.search(board, lv.depth, lv.seconds)
    res = engine.search(board, lv.depth, lv.seconds, multi=True)
    if res.scores and abs(res.score) < MATE_ZONE:
        move, score = max(res.scores, key=lambda t: t[1] + rng.uniform(-lv.noise, lv.noise))
        res.move, res.score = move, score
        if res.pv and res.pv[0] != move:
            res.pv = [move]
    return res
