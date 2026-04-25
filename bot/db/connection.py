"""
Подключение к SQLite и инициализация БД.
"""

import os
import logging
import aiosqlite

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.getenv('DB_PATH', os.path.join(_PROJECT_ROOT, 'data', 'bot.db'))

_cached_db: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    """Возвращает кэшированное подключение к БД (создаётся один раз)."""
    global _cached_db
    if _cached_db is None:
        _cached_db = await aiosqlite.connect(DB_PATH)
        await _cached_db.execute('PRAGMA foreign_keys = ON')
    return _cached_db


async def close_connection():
    """Закрывает кэшированное подключение."""
    global _cached_db
    if _cached_db is not None:
        await _cached_db.close()
        _cached_db = None
