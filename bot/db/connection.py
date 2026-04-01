"""
Подключение к SQLite и инициализация БД.
"""

import os
import logging
import aiosqlite

logger = logging.getLogger(__name__)

# Корень проекта: bot/db/connection.py → bot/db/ → bot/ → project_root/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.getenv('DB_PATH', os.path.join(_PROJECT_ROOT, 'data', 'bot.db'))


async def _connect():
    """Подключение к БД с включёнными foreign keys."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute('PRAGMA foreign_keys = ON')
    return db
