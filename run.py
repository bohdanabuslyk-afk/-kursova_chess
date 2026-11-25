"""Запуск: python run.py [порт]  ->  http://127.0.0.1:8000"""
import sys

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Шахи запущено: http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")
