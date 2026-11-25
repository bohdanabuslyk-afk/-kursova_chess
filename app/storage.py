"""Автозбереження партій у data/games/<id>.pgn."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import chess.pgn

from .game import Game, MoveError

FOLDER = Path(__file__).resolve().parent.parent / "data" / "games"
_ID = re.compile(r"[0-9a-f]{12}")


def save(game: Game) -> None:
    if not game.board.move_stack or game.imported:
        return
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / f"{game.id}.pgn").write_text(game.pgn(), encoding="utf-8")


def load(game_id: str) -> Game | None:
    # Перевірка формату не дає вийти за межі папки через «../».
    path = FOLDER / f"{game_id}.pgn"
    if not _ID.fullmatch(game_id) or not path.is_file():
        return None
    try:
        game = Game.from_pgn(path.read_text(encoding="utf-8"), imported=False)
    except MoveError:
        return None
    game.id = game_id
    game.created = datetime.fromtimestamp(path.stat().st_mtime)
    return game


def listing(limit: int = 30) -> list[dict]:
    files = sorted(FOLDER.glob("*.pgn"), key=lambda p: p.stat().st_mtime, reverse=True) if FOLDER.is_dir() else []
    rows = []
    for path in files[:limit]:
        with path.open(encoding="utf-8") as f:
            game = chess.pgn.read_game(f)
        if game is None:
            continue
        h = game.headers
        rows.append({
            "id": path.stem, "white": h["White"], "black": h["Black"], "result": h["Result"],
            "reason": h.get("Termination"), "moves": (game.end().ply() + 1) // 2,
            "time": datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
        })
    return rows
