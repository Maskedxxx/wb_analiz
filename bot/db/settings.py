"""
Настройки бота (key-value).
"""

import aiosqlite

from bot.db.connection import DB_PATH


async def get_setting(key: str, default: str = None) -> str | None:
    """Получает настройку по ключу."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT value FROM settings WHERE key = ?',
            (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    """Сохраняет настройку (insert or replace)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )
        await db.commit()
