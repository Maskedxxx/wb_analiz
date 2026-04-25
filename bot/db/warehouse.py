"""
Данные по складам (warehouse_stocks).

Стратегия: replace — хранится только последний снимок для каждого store_id.
Метка свежести — в таблице cache_meta.
"""

import aiosqlite

from bot.db.connection import get_connection


async def save_warehouse_data(store_id: int, rows: list[dict]):
    """Заменяет снимок остатков по складам (delete old + insert new)."""
    db = await get_connection()
    await db.execute('DELETE FROM warehouse_stocks WHERE store_id = ?', (store_id,))
    for row in rows:
        await db.execute(
            '''INSERT INTO warehouse_stocks
               (store_id, nm_id, warehouse_name, quantity, in_way_from_client,
                supplier_article, warehouse_id, region_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (store_id, row['nm_id'], row.get('warehouse_name', ''),
             row.get('quantity', 0), row.get('in_way_from_client', 0),
             row.get('supplier_article'),
             row.get('warehouse_id'), row.get('region_name', ''))
        )
    await db.execute(
        "INSERT OR REPLACE INTO cache_meta (store_id, data_type, fetched_at) "
        "VALUES (?, 'warehouse', datetime('now'))",
        (store_id,)
    )
    await db.commit()


async def get_latest_warehouse_data(store_id: int) -> list[dict]:
    """Возвращает текущий снимок остатков по складам."""
    db = await get_connection()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        'SELECT nm_id, warehouse_name, quantity, in_way_from_client, '
        'supplier_article, warehouse_id, region_name '
        'FROM warehouse_stocks WHERE store_id = ?',
        (store_id,)
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_unique_warehouses() -> list[dict]:
    """Возвращает уникальные склады по всем магазинам (для справочника).

    Returns:
        [{id, name, region}] — дедуп по warehouse_id, сортировка: регион → имя.
    """
    db = await get_connection()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        'SELECT DISTINCT warehouse_id, warehouse_name, region_name '
        'FROM warehouse_stocks '
        'WHERE warehouse_id IS NOT NULL '
        'ORDER BY region_name, warehouse_name'
    )
    rows = await cursor.fetchall()
    seen = set()
    result = []
    for r in rows:
        wid = r['warehouse_id']
        if wid in seen:
            continue
        seen.add(wid)
        result.append({
            'id': wid,
            'name': r['warehouse_name'],
            'region': r['region_name'] or '',
        })
    return result


async def is_warehouse_data_fresh(store_id: int, ttl_minutes: int) -> bool:
    """Проверяет, есть ли данные по складам свежее ttl_minutes минут."""
    db = await get_connection()
    cursor = await db.execute(
        "SELECT 1 FROM cache_meta WHERE store_id = ? AND data_type = 'warehouse' "
        "AND fetched_at > datetime('now', ?)",
        (store_id, f'-{ttl_minutes} minutes')
    )
    return await cursor.fetchone() is not None
