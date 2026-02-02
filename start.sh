#!/bin/bash
# Скрипт запуска телеграм-бота WB Analiz

set -e

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo ""
    echo "Создайте файл .env с переменными:"
    echo "  TELEGRAM_TOKEN=ваш_токен_бота"
    echo "  CHAT_ID=id_чата"
    exit 1
fi

# Проверяем наличие токена WB
if [ ! -f nemov_token.txt ]; then
    echo "❌ Файл nemov_token.txt не найден!"
    exit 1
fi

echo "🚀 Запуск бота..."
docker-compose up -d --build

echo ""
echo "✅ Бот запущен!"
echo ""
echo "Полезные команды:"
echo "  docker-compose logs -f    — смотреть логи"
echo "  docker-compose down       — остановить"
echo "  docker-compose restart    — перезапустить"
