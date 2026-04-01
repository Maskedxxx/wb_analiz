"""
Аудит-лог действий пользователей.
"""

import aiosqlite

from bot.db.connection import DB_PATH


async def log_action(chat_id: int, action: str, details: str = None):
    """Записывает действие в аудит-лог."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO audit_log (chat_id, action, details) VALUES (?, ?, ?)',
            (chat_id, action, details)
        )
        await db.commit()
