#!/bin/sh
# Перевірка, коміт і push етапу: sh tools/push.sh "повідомлення"
python -m unittest -q || exit 1
git add -A
git commit -q -m "$1" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && GIT_TERMINAL_PROMPT=0 git push -q && git log --oneline -1
