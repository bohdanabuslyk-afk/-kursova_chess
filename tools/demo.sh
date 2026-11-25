#!/bin/sh
# Сервери для знімків: 8000 – без моделі, 8001 – з тестовою заглушкою замість моделі.
python -m tools.mock_llm 8111 &
CHESS_LLM_BASE_URL= CHESS_LLM_API_KEY= CHESS_LLM_MODEL= python run.py 8000 &
CHESS_LLM_BASE_URL=http://127.0.0.1:8111/v1 CHESS_LLM_API_KEY=test CHESS_LLM_MODEL="тестова заглушка" python run.py 8001 &
wait
