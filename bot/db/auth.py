"""
Авторизация пользователей с in-memory кэшем.
"""

import time
import aiosqlite

from bot.db.connection import DB_PATH

_authorized_cache: set[int] = set()
_auth_cache_loaded = False
_auth_cache_ts: float = 0
_AUTH_CACHE_TTL = 300  # перезагрузка кэша каждые 5 минут


async def _ensure_auth_cache():
    """Загружает кэш авторизованных пользователей из БД (с TTL)."""
    global _auth_cache_loaded, _auth_cache_ts
    now = time.monotonic()
    if _auth_cache_loaded and (now - _auth_cache_ts < _AUTH_CACHE_TTL):
        return
    global _authorized_cache
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT chat_id FROM authorized_users')
        rows = await cursor.fetchall()
    _authorized_cache = {row[0] for row in rows}
    _auth_cache_loaded = True
    _auth_cache_ts = now


async def is_authorized(chat_id: int) -> bool:
    """Проверяет авторизацию из in-memory кэша (без SQL на каждый запрос)."""
    await _ensure_auth_cache()
    return chat_id in _authorized_cache


async def authorize_user(chat_id: int):
    """Добавляет пользователя в список авторизованных + обновляет кэш."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO authorized_users (chat_id) VALUES (?)',
            (chat_id,)
        )
        await db.commit()
    _authorized_cache.add(chat_id)
