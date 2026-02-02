"""
Обработчики команд и сообщений телеграм-бота.
"""

import os
import csv
import asyncio
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

from bot.config import FEEDBACK_DIR
from bot.report import generate_report

# Роутер для обработчиков
router = Router()

# Эмодзи для фидбека
FEEDBACK_EMOJIS = {'👍', '👎', '🤷'}


def save_feedback(emoji: str = '', comment: str = ''):
    """
    Сохраняет фидбек в CSV файл.

    Args:
        emoji: эмодзи реакции (👍/👎/🤷)
        comment: текстовый комментарий
    """
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    feedback_file = os.path.join(FEEDBACK_DIR, 'feedback.csv')

    # Создаём файл с заголовками если не существует
    file_exists = os.path.exists(feedback_file)

    with open(feedback_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'emoji', 'comment'])
        writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M'), emoji, comment])


@router.message(Command('start'))
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer(
        "📊 Бот WB Analiz\n\n"
        "Каждый день в 8:00 МСК отправляю отчёт по ценам.\n\n"
        "Команды:\n"
        "/report — получить отчёт сейчас\n\n"
        "После получения отчёта можно ответить:\n"
        "👍 — всё ок\n"
        "👎 — что-то не так\n"
        "🤷 — не понял\n"
        "Или написать комментарий текстом."
    )


@router.message(Command('report'))
async def cmd_report(message: Message):
    """Обработчик команды /report — ручной запрос отчёта."""
    await message.answer("⏳ Генерирую отчёт (загрузка данных из WB API)...")

    try:
        # Запускаем синхронную функцию в отдельном потоке
        report_path = await asyncio.to_thread(generate_report)
        document = FSInputFile(report_path, filename=os.path.basename(report_path))
        await message.answer_document(document, caption="📊 Отчёт готов!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(F.text.in_(FEEDBACK_EMOJIS))
async def handle_emoji_feedback(message: Message):
    """Обработчик эмодзи-реакций."""
    save_feedback(emoji=message.text)
    await message.answer("✅ Фидбек сохранён!")


@router.message(F.text)
async def handle_text_feedback(message: Message):
    """Обработчик текстовых комментариев."""
    # Игнорируем команды (начинаются с /)
    if message.text.startswith('/'):
        return

    save_feedback(comment=message.text)
    await message.answer("✅ Комментарий сохранён!")
