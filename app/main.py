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

from . import llm, storage
from .analysis import SPEEDS, Analysis
from .engine import LEVELS, Engine
from .game import Game, MoveError

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 200_000
games: dict[str, Game] = {}


def get_game(request: Request) -> Game:
    gid = request.path_params["id"]
    game = games.get(gid)
    if game is None:
        game = storage.load(gid)  # після перезапуску сервера партія береться з архіву
        if game is None:
            raise HTTPException(404, "Партію не знайдено")
        games[gid] = game
    return game


async def body_of(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Запит завеликий")
    try:
        data = await request.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise HTTPException(400, "Очікується JSON-об'єкт")
    return data


def saved(game: Game) -> Response:
    storage.save(game)
    return JSONResponse(game.state())


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


async def levels(request: Request) -> Response:
    return JSONResponse([{"id": i, "name": lv.name, "description": lv.description} for i, lv in LEVELS.items()])


async def llm_status(request: Request) -> Response:
    return JSONResponse(llm.llm.status())


async def create_game(request: Request) -> Response:
    body = await body_of(request)
    if body.get("opponent") == "llm" and not llm.llm.ready:
        raise HTTPException(400, "Мовну модель не підключено: заповніть файл .env")
    game = Game(body.get("color", "white"), body.get("opponent", "engine"), body.get("level", 3))
    games[game.id] = game
    return JSONResponse(game.state())


async def list_games(request: Request) -> Response:
    return JSONResponse(await asyncio.to_thread(storage.listing))


async def import_game(request: Request) -> Response:
    body = await body_of(request)
    game = Game.from_pgn(str(body.get("pgn", "")))
    games[game.id] = game
    return JSONResponse(game.state())


async def game_state(request: Request) -> Response:
    return JSONResponse(get_game(request).state())


async def make_move(request: Request) -> Response:
    game = get_game(request)
    body = await body_of(request)
    game.play(str(body.get("move", "")))
    return saved(game)


async def reply(request: Request) -> Response:
    """Хід суперника рахується в окремому потоці, щоб не блокувати сервер."""
    game = get_game(request)
    await asyncio.to_thread(game.reply)
    return saved(game)


async def undo(request: Request) -> Response:
    game = get_game(request)
    game.undo()
    return saved(game)


async def resign(request: Request) -> Response:
    game = get_game(request)
    game.resign()
    return saved(game)


async def hint(request: Request) -> Response:
    game = get_game(request)
    board = game.board.copy()
    if game.outcome()[0]:
        raise MoveError("Партію вже завершено")
    res = await asyncio.to_thread(Engine().search, board, 6, 1.5)
    return JSONResponse({"uci": res.move.uci(), "san": board.san(res.move), "pv": board.variation_san(res.pv)})


async def analysis_start(request: Request) -> Response:
    game = get_game(request)
    speed = (await body_of(request)).get("speed", "fast")
    if speed not in SPEEDS:
        raise HTTPException(400, "Невідомий режим аналізу")
    with game.lock:
        if not game.board.move_stack:
            raise MoveError("У партії ще немає ходів")
        if game.analysis:
            game.analysis.cancelled = True
        game.analysis = Analysis(game.board, speed)
        game.analysis.start()
    return JSONResponse(game.analysis.state())


async def analysis_state(request: Request) -> Response:
    analysis = get_game(request).analysis
    return JSONResponse(analysis.state() if analysis else {"started": False})


async def explain(request: Request) -> Response:
    game = get_game(request)
    ply = (await body_of(request)).get("ply")
    with game.lock:
        rows = game.analysis.rows if game.analysis else []
        if not isinstance(ply, int) or not 1 <= ply <= len(rows):
            raise HTTPException(400, "Цей хід ще не проаналізовано")
        row = rows[ply - 1]
        board = chess.Board()
        for move in game.analysis.moves[:ply - 1]:
            board.push(move)
    return JSONResponse(await asyncio.to_thread(llm.explain, board, row))


async def coach_chat(request: Request) -> Response:
    game = get_game(request)
    question = str((await body_of(request)).get("question", "")).strip()[:500]
    if not question:
        raise HTTPException(400, "Порожнє запитання")
    with game.lock:
        board = game.board.copy()
    answer = await asyncio.to_thread(llm.chat, board, list(game.chat), question)
    game.chat += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return JSONResponse({"answer": answer})


async def llm_error(request: Request, exc: Exception) -> Response:
    return JSONResponse({"error": str(exc)}, status_code=502)


async def pgn(request: Request) -> Response:
    game = get_game(request)
    return Response(game.pgn(), media_type="application/x-chess-pgn",
                    headers={"Content-Disposition": f'attachment; filename="partiia-{game.id}.pgn"'})


async def move_error(request: Request, exc: Exception) -> Response:
    return JSONResponse({"error": str(exc)}, status_code=400)


async def http_error(request: Request, exc: HTTPException) -> Response:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/pieces/{symbol}.svg", piece),
        Route("/api/levels", levels),
        Route("/api/llm", llm_status),
        Route("/api/games", list_games),
        Route("/api/games", create_game, methods=["POST"]),
        Route("/api/import", import_game, methods=["POST"]),
        Route("/api/games/{id}", game_state),
        Route("/api/games/{id}/move", make_move, methods=["POST"]),
        Route("/api/games/{id}/reply", reply, methods=["POST"]),
        Route("/api/games/{id}/undo", undo, methods=["POST"]),
        Route("/api/games/{id}/resign", resign, methods=["POST"]),
        Route("/api/games/{id}/hint", hint, methods=["POST"]),
        Route("/api/games/{id}/analysis", analysis_state),
        Route("/api/games/{id}/analysis", analysis_start, methods=["POST"]),
        Route("/api/games/{id}/explain", explain, methods=["POST"]),
        Route("/api/games/{id}/chat", coach_chat, methods=["POST"]),
        Route("/api/games/{id}/pgn", pgn),
        Mount("/static", StaticFiles(directory=STATIC)),
    ],
    exception_handlers={MoveError: move_error, llm.LLMError: llm_error, HTTPException: http_error},
)
