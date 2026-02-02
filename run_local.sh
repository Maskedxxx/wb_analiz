#!/bin/bash
# Локальный запуск бота без Docker

# Активация venv
source /Users/mask/Documents/ПРОЕКТЫ_2024/СОЮЗ_СНАБ_workRepo/knowledge_map_release_v2/ai-neuro/semantic_venv/bin/activate

# Переход в директорию проекта
cd "$(dirname "$0")"

# Загрузка переменных из .env (если есть)
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Пути (если не заданы в .env)
export WB_TOKEN_FILE="${WB_TOKEN_FILE:-$(pwd)/nemov_token.txt}"
export REPORTS_DIR="${REPORTS_DIR:-$(pwd)/reports}"
export FEEDBACK_DIR="${FEEDBACK_DIR:-$(pwd)/feedback}"
export LOGS_DIR="${LOGS_DIR:-$(pwd)/logs}"

# Запуск бота
python -m bot.main
