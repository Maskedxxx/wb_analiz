"""
CRUD операции с магазинами.
"""

import aiosqlite

from bot.core.security import obfuscate_token, deobfuscate_token
from bot.db.connection import DB_PATH


async def add_store(token: str, name: str = None) -> int:
    """Добавляет магазин. Токен обфусцируется перед сохранением."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO stores (token, name) VALUES (?, ?)',
            (obfuscate_token(token), name)
        )
        await db.commit()
        return cursor.lastrowid


async def get_stores() -> list:
    """Возвращает список активных магазинов (токены деобфусцируются)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT id, token, name, marketplace_name, added_at FROM stores WHERE is_active = 1'
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d['token'] = deobfuscate_token(d['token'])
            result.append(d)
        return result


async def get_store(store_id: int) -> dict | None:
    """Возвращает магазин по id (токен деобфусцируется)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT id, token, name, marketplace_name, added_at FROM stores WHERE id = ? AND is_active = 1',
            (store_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d['token'] = deobfuscate_token(d['token'])
        return d


async def update_store(store_id: int, **kwargs):
    """Обновляет поля магазина (name, token, marketplace_name)."""
    allowed = {'name', 'token', 'marketplace_name'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if 'token' in fields and fields['token']:
        fields['token'] = obfuscate_token(fields['token'])
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [store_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f'UPDATE stores SET {set_clause} WHERE id = ?',
            values
        )
        await db.commit()


async def delete_store(store_id: int):
    """Мягкое удаление магазина (is_active = 0)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE stores SET is_active = 0 WHERE id = ?',
            (store_id,)
        )
        await db.commit()
