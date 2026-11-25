"""Перевірка підключення мовної моделі одним коротким запитом: python -m tools.check_llm

Ключ на екран не виводиться.
"""
import sys
import time

from app.llm import LLMError, llm


def main() -> None:
    c = llm.config
    for name, value in (("CHESS_LLM_BASE_URL", c.base_url), ("CHESS_LLM_API_KEY", c.api_key), ("CHESS_LLM_MODEL", c.model)):
        print(f"{name}: {'заповнено' if value else 'ПОРОЖНЬО'}")
    if not llm.ready:
        sys.exit("Заповніть порожні рядки у файлі .env")
    print("Модель:", c.model)
    start = time.perf_counter()
    try:
        answer = llm.ask([{"role": "user", "content": "Відповідай одним словом: як називається фігура, що ходить буквою Г?"}])
    except LLMError as e:
        sys.exit(f"Не вдалося: {e}")
    print(f"Працює ({time.perf_counter() - start:.1f} с). Відповідь: {answer[:100]}")


if __name__ == "__main__":
    main()
