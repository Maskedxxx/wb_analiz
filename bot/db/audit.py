"""
Аудит-лог действий пользователей.
"""

import aiosqlite

from bot.db.connection import get_connection


async def log_action(chat_id: int, action: str, details: str = None):
    """Записывает действие в аудит-лог."""
    db = await get_connection()
    await db.execute(
        'INSERT INTO audit_log (chat_id, action, details) VALUES (?, ?, ?)',
        (chat_id, action, details)
    )
    await db.commit()
