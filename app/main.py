"""HTTP-сервер застосунку."""
from __future__ import annotations

import asyncio
from pathlib import Path

import chess
import chess.svg
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .engine import LEVELS
from .game import Game, MoveError

STATIC = Path(__file__).resolve().parent.parent / "static"
games: dict[str, Game] = {}


def get_game(request: Request) -> Game:
    game = games.get(request.path_params["id"])
    if game is None:
        raise HTTPException(404, "Партію не знайдено")
    return game


async def index(request: Request) -> Response:
    return FileResponse(STATIC / "index.html")


async def piece(request: Request) -> Response:
    """Зображення фігури з набору python-chess (автор Colin M.L. Burnett)."""
    symbol = request.path_params["symbol"]
    if symbol not in {c + p for c in "wb" for p in "pnbrqk"}:
        raise HTTPException(404)
    letter = symbol[1].upper() if symbol[0] == "w" else symbol[1]
    svg = chess.svg.piece(chess.Piece.from_symbol(letter))
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


async def body_of(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise HTTPException(400, "Очікується JSON-об'єкт")
    return data


async def levels(request: Request) -> Response:
    return JSONResponse([{"id": i, "name": lv.name, "description": lv.description} for i, lv in LEVELS.items()])


async def create_game(request: Request) -> Response:
    body = await body_of(request)
    game = Game(body.get("color", "white"), body.get("opponent", "engine"), body.get("level", 3))
    games[game.id] = game
    return JSONResponse(game.state())


async def game_state(request: Request) -> Response:
    return JSONResponse(get_game(request).state())


async def make_move(request: Request) -> Response:
    game = get_game(request)
    body = await body_of(request)
    game.play(str(body.get("move", "")))
    return JSONResponse(game.state())


async def reply(request: Request) -> Response:
    """Хід суперника рахується в окремому потоці, щоб не блокувати сервер."""
    game = get_game(request)
    await asyncio.to_thread(game.reply)
    return JSONResponse(game.state())


async def move_error(request: Request, exc: Exception) -> Response:
    return JSONResponse({"error": str(exc)}, status_code=400)


async def http_error(request: Request, exc: HTTPException) -> Response:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/pieces/{symbol}.svg", piece),
        Route("/api/levels", levels),
        Route("/api/games", create_game, methods=["POST"]),
        Route("/api/games/{id}", game_state),
        Route("/api/games/{id}/move", make_move, methods=["POST"]),
        Route("/api/games/{id}/reply", reply, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC)),
    ],
    exception_handlers={MoveError: move_error, HTTPException: http_error},
)
