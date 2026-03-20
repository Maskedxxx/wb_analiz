#!/bin/bash
# Локальный запуск бота без Docker
# Работает на Windows (Git Bash) и macOS/Linux

set -e

# Переход в директорию проекта
cd "$(dirname "$0")"

# Создаём venv если не существует
if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python -m venv .venv
fi

# Активация venv (Windows Git Bash или Unix)
if [ -f ".venv/Scripts/activate" ]; then
    # Windows
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    # macOS / Linux
    source .venv/bin/activate
else
    echo "Ошибка: не удалось найти виртуальное окружение"
    exit 1
fi

# Установка зависимостей
pip install -q -r requirements.txt

# Загрузка переменных из .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Ошибка: файл .env не найден. Создайте его из .env.example"
    exit 1
fi

# Пути (если не заданы в .env)
export REPORTS_DIR="${REPORTS_DIR:-$(pwd)/reports}"
export FEEDBACK_DIR="${FEEDBACK_DIR:-$(pwd)/feedback}"
export LOGS_DIR="${LOGS_DIR:-$(pwd)/logs}"
export DB_PATH="${DB_PATH:-$(pwd)/data/bot.db}"

# Создаём директории если нет
mkdir -p "$REPORTS_DIR" "$FEEDBACK_DIR" "$LOGS_DIR" "$(dirname "$DB_PATH")"

echo "Запуск бота..."
python -m bot.main
