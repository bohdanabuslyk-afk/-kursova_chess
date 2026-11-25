"""Тестова заглушка з OpenAI-сумісним API: python -m tools.mock_llm [порт]

Це НЕ мовна модель. Вона повертає заготовлені відповіді, щоб перевірити код застосунку без ключа:
перша спроба кожного третього ходу навмисно нелегальна, щоб було видно захист і повтор запиту.
"""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

counter = {"moves": 0}


def answer(messages: list[dict]) -> str:
    system, last = messages[0]["content"], messages[-1]["content"]
    if "суперник" in system:
        retry = last.startswith("Хід не прийнято")
        listing = next(m["content"] for m in messages if "Дозволені ходи:" in m["content"]).split("Дозволені ходи:")[1]
        ucis = re.findall(r"\(([a-h][1-8][a-h][1-8][qrbn]?)\)", listing)
        if not retry:
            counter["moves"] += 1
            if counter["moves"] % 3 == 2:
                return json.dumps({"move": "a1a1", "comment": "навмисно хибна відповідь"}, ensure_ascii=False)
        move = next((m for m in ucis if m[2:4] in ("e5", "d5", "c6", "f6", "e4", "d4")), ucis[0])
        return "```json\n" + json.dumps({"move": move, "comment": "[заглушка] Займаю центр."}, ensure_ascii=False) + "\n```"
    if "Запитання учня" in last:
        return "[заглушка] Тут була б відповідь тренера від мовної моделі."
    return "[заглушка] Тут було б пояснення ходу від мовної моделі."


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.dumps({
            "id": "mock", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer(body["messages"])}}],
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def serve(port: int = 8111) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8111).serve_forever()
