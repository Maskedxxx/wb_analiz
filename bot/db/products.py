"""
Кэш данных о товарах (product_data).

Стратегия: replace — хранится только последний снимок для каждого store_id.
Метка свежести — в таблице cache_meta.
"""

import aiosqlite

from bot.db.connection import get_connection


async def save_product_data(store_id: int, rows: list[dict]):
    """Заменяет снимок данных по товарам магазина (delete old + insert new)."""
    db = await get_connection()
    await db.execute('DELETE FROM product_data WHERE store_id = ?', (store_id,))
    for row in rows:
        await db.execute(
            '''INSERT INTO product_data
               (store_id, nm_id, supplier_article, subject, category,
                product_group, stock_qty, in_way_from_client, stock_qty_clean,
                orders_7d, orders_14d, orders_30d,  -- orders_30d: больше не запрашивается, всегда NULL
                avg_per_day, days_remaining, price_increase_pct, price, barcode,
                availability, sale_rate_days, office_missing_days, lost_orders, trend_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (store_id, row['nm_id'], row.get('supplier_article'),
             row.get('subject'), row.get('category'),
             row.get('product_group'), row.get('stock_qty'),
             row.get('in_way_from_client', 0), row.get('stock_qty_clean'),
             row.get('orders_7d'), row.get('orders_14d'), row.get('orders_30d'),
             row.get('avg_per_day'), row.get('days_remaining'),
             row.get('price_increase_pct'), row.get('price'),
             row.get('barcode'),
             row.get('availability', '') or '',
             row.get('sale_rate_days', 0) or 0,
             row.get('office_missing_days', 0) or 0,
             row.get('lost_orders', 0) or 0,
             row.get('trend_pct', 0) or 0)
        )
    await db.execute(
        "INSERT OR REPLACE INTO cache_meta (store_id, data_type, fetched_at) "
        "VALUES (?, 'product', datetime('now'))",
        (store_id,)
    )
    await db.commit()


async def get_latest_product_data(store_id: int) -> tuple[list[dict], str | None]:
    """
    Возвращает текущий снимок данных по магазину.

    Returns:
        (rows, fetched_at) — список товаров и время загрузки, или ([], None)
    """
    db = await get_connection()
    cursor = await db.execute(
        "SELECT fetched_at FROM cache_meta WHERE store_id = ? AND data_type = 'product'",
        (store_id,)
    )
    meta = await cursor.fetchone()
    if not meta:
        return [], None

    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        'SELECT * FROM product_data WHERE store_id = ?',
        (store_id,)
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return rows, meta[0]


async def is_data_fresh(store_id: int, ttl_minutes: int) -> bool:
    """Проверяет, есть ли данные свежее ttl_minutes минут."""
    db = await get_connection()
    cursor = await db.execute(
        "SELECT 1 FROM cache_meta WHERE store_id = ? AND data_type = 'product' "
        "AND fetched_at > datetime('now', ?)",
        (store_id, f'-{ttl_minutes} minutes')
    )
    return await cursor.fetchone() is not None
