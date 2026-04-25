"""
Управление подписчиками на ежедневные отчёты.
"""

import aiosqlite

from bot.db.connection import get_connection


async def add_subscriber(chat_id: int):
    """Добавляет подписчика на ежедневные отчёты."""
    db = await get_connection()
    await db.execute(
        'INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)',
        (chat_id,)
    )
    await db.commit()


async def remove_subscriber(chat_id: int):
    """Удаляет подписчика."""
    db = await get_connection()
    await db.execute(
        'DELETE FROM subscribers WHERE chat_id = ?',
        (chat_id,)
    )
    await db.commit()


async def get_subscribers() -> list[int]:
    """Возвращает список chat_id всех подписчиков."""
    db = await get_connection()
    cursor = await db.execute('SELECT chat_id FROM subscribers')
    rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def is_subscriber(chat_id: int) -> bool:
    """Проверяет, подписан ли пользователь."""
    db = await get_connection()
    cursor = await db.execute(
        'SELECT 1 FROM subscribers WHERE chat_id = ?',
        (chat_id,)
    )
    return await cursor.fetchone() is not None
