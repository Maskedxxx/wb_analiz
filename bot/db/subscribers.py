"""
Управление подписчиками на ежедневные отчёты.
"""

import aiosqlite

from bot.db.connection import DB_PATH


async def add_subscriber(chat_id: int):
    """Добавляет подписчика на ежедневные отчёты."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)',
            (chat_id,)
        )
        await db.commit()


async def remove_subscriber(chat_id: int):
    """Удаляет подписчика."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'DELETE FROM subscribers WHERE chat_id = ?',
            (chat_id,)
        )
        await db.commit()


async def get_subscribers() -> list[int]:
    """Возвращает список chat_id всех подписчиков."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT chat_id FROM subscribers')
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def is_subscriber(chat_id: int) -> bool:
    """Проверяет, подписан ли пользователь."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT 1 FROM subscribers WHERE chat_id = ?',
            (chat_id,)
        )
        return await cursor.fetchone() is not None
