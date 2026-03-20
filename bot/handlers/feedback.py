"""
Сбор фидбека: эмодзи-реакции и текстовые комментарии.
"""

import os
import csv
import asyncio
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message

from bot.keyboards import back_to_menu_kb
from bot.config import FEEDBACK_DIR, FEEDBACK_RETENTION_MONTHS

logger = logging.getLogger(__name__)

router = Router()

FEEDBACK_EMOJIS = {'👍', '👎', '🤷'}


def _feedback_filename() -> str:
    """Имя файла для текущего месяца: feedback_2026_03.csv"""
    return os.path.join(FEEDBACK_DIR, datetime.now().strftime('feedback_%Y_%m.csv'))


def cleanup_old_feedback():
    """Удаляет файлы фидбека старше FEEDBACK_RETENTION_MONTHS месяцев."""
    if not os.path.isdir(FEEDBACK_DIR):
        return
    now = datetime.now()
    for fname in os.listdir(FEEDBACK_DIR):
        if not fname.startswith('feedback_') or not fname.endswith('.csv'):
            continue
        try:
            parts = fname[len('feedback_'):-len('.csv')].split('_')
            file_date = datetime(int(parts[0]), int(parts[1]), 1)
        except (ValueError, IndexError):
            continue
        months_old = (now.year - file_date.year) * 12 + (now.month - file_date.month)
        if months_old >= FEEDBACK_RETENTION_MONTHS:
            os.remove(os.path.join(FEEDBACK_DIR, fname))
            logger.info(f"Удалён устаревший файл фидбека: {fname}")


def _save_feedback_sync(emoji: str = '', comment: str = ''):
    """Синхронная запись фидбека (вызывается через asyncio.to_thread)."""
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    feedback_file = _feedback_filename()
    file_exists = os.path.exists(feedback_file)
    with open(feedback_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'emoji', 'comment'])
        writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M'), emoji, comment])


async def save_feedback(emoji: str = '', comment: str = ''):
    """Сохраняет фидбек в файл текущего месяца (не блокирует event loop)."""
    await asyncio.to_thread(_save_feedback_sync, emoji, comment)


@router.message(F.text.in_(FEEDBACK_EMOJIS))
async def handle_emoji_feedback(message: Message):
    """Обработчик эмодзи-реакций."""
    await save_feedback(emoji=message.text)
    await message.answer("✅ Фидбек сохранён!", reply_markup=back_to_menu_kb())


@router.message(F.text)
async def handle_text_feedback(message: Message):
    """Обработчик текстовых комментариев (catch-all)."""
    if message.text.startswith('/'):
        return
    await save_feedback(comment=message.text)
    await message.answer("✅ Комментарий сохранён!", reply_markup=back_to_menu_kb())
