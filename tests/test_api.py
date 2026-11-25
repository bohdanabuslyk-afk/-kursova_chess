"""HTTP-інтерфейс: застосунок викликається напряму за протоколом ASGI, без мережі."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import llm, main, storage


def call(method: str, path: str, body=None):
    raw = body if isinstance(body, bytes) else b"" if body is None else json.dumps(body).encode()
    sent = []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "root_path": "", "query_string": b"", "scheme": "http",
             "headers": [(b"host", b"test")], "client": ("127.0.0.1", 1), "server": ("test", 80)}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(main.app(scope, receive, send))
    content = b"".join(m.get("body", b"") for m in sent)
    try:
        data = json.loads(content)
    except ValueError:
        data = content.decode(errors="replace")
    return sent[0]["status"], data


class Api(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for p in (mock.patch.object(storage, "FOLDER", Path(tmp.name)),
                  mock.patch.object(llm, "llm", llm.LLM(llm.Config()))):
            p.start()
            self.addCleanup(p.stop)

    def new(self, **kw):
        return call("POST", "/api/games", {"opponent": "human", **kw})[1]["id"]

    def test_play_undo_pgn(self):
        gid = self.new()
        status, st = call("POST", f"/api/games/{gid}/move", {"move": "e2e4"})
        self.assertEqual((status, st["history"][0]["san"]), (200, "e4"))
        self.assertIn("1. e4", call("GET", f"/api/games/{gid}/pgn")[1])
        self.assertEqual(call("POST", f"/api/games/{gid}/undo", {})[1]["history"], [])

    def test_computer_replies(self):
        gid = self.new(opponent="engine", level=1, color="black")
        self.assertEqual(len(call("POST", f"/api/games/{gid}/reply", {})[1]["history"]), 1)

    def test_game_survives_restart(self):
        gid = self.new()
        call("POST", f"/api/games/{gid}/move", {"move": "d4"})
        main.games.clear()
        self.assertEqual(call("GET", f"/api/games/{gid}")[1]["history"][0]["san"], "d4")

    def test_bad_requests(self):
        gid = self.new()
        for path, body, want in (
            (f"/api/games/{gid}/move", {"move": "e2e5"}, 400), (f"/api/games/{gid}/move", b"[1]", 400),
            (f"/api/games/{gid}/move", b"{oops", 400), (f"/api/games/{gid}/move", b"\xff\xfe", 400),
            (f"/api/games/{gid}/analysis", {"speed": "fast"}, 400), (f"/api/games/{gid}/analysis", {"speed": "x"}, 400),
            (f"/api/games/{gid}/explain", {"ply": 1}, 400), (f"/api/games/{gid}/chat", {"question": " "}, 400),
            (f"/api/games/{gid}/chat", {"question": "План?"}, 502), ("/api/games", {"level": [1]}, 400),
            ("/api/games", {"level": 99}, 400), ("/api/games", {"opponent": "llm"}, 400),
            ("/api/import", {"pgn": "xx"}, 400), ("/api/import", b"x" * 300_000, 413),
            ("/api/games/000000000000/move", {"move": "e4"}, 404),
        ):
            status, data = call("POST", path, body)
            self.assertEqual(status, want, (path, body if not isinstance(body, bytes) else body[:9], data))
            self.assertTrue(data["error"])

    def test_pieces(self):
        self.assertEqual(call("GET", "/pieces/wk.svg")[0], 200)
        self.assertEqual(call("GET", "/pieces/xx.svg")[0], 404)

    def test_env_file_is_not_served(self):
        for path in ("/.env", "/static/../.env", "/static/%2e%2e/.env"):
            self.assertEqual(call("GET", path)[0], 404)


if __name__ == "__main__":
    unittest.main()
