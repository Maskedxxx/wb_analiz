"""
Миграции БД: создание таблиц, структурные изменения.
"""

import os
import logging
import aiosqlite

from bot.core.security import obfuscate_token
from bot.db.connection import DB_PATH

logger = logging.getLogger(__name__)


# === Миграции ===

async def _migrate_add_column_safe(db, table, column, col_type):
    """Добавляет колонку если её ещё нет (идемпотентно)."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in await cursor.fetchall()]
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


async def _migrate_obfuscate_tokens(db):
    """Обфусцирует plaintext-токены (без префикса 'obf:')."""
    cursor = await db.execute("SELECT id, token FROM stores WHERE token NOT LIKE 'obf:%'")
    plain_rows = await cursor.fetchall()
    for row_id, raw_token in plain_rows:
        await db.execute('UPDATE stores SET token = ? WHERE id = ?', (obfuscate_token(raw_token), row_id))
    if plain_rows:
        logger.info(f"Обфусцировано токенов: {len(plain_rows)}")


async def _migrate_marketplace_name(db):
    await _migrate_add_column_safe(db, 'stores', 'marketplace_name', 'TEXT')


async def _migrate_product_price(db):
    await _migrate_add_column_safe(db, 'product_data', 'price', 'REAL')


async def _migrate_warehouse_stocks(db):
    await db.execute('''
        CREATE TABLE IF NOT EXISTS warehouse_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER REFERENCES stores(id),
            nm_id INTEGER NOT NULL,
            warehouse_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    await db.execute('''
        CREATE INDEX IF NOT EXISTS idx_warehouse_stocks_store_date
            ON warehouse_stocks(store_id, fetched_at)
    ''')


async def _migrate_warehouse_in_way(db):
    await _migrate_add_column_safe(db, 'warehouse_stocks', 'in_way_from_client', 'INTEGER DEFAULT 0')


async def _migrate_warehouse_supplier_article(db):
    await _migrate_add_column_safe(db, 'warehouse_stocks', 'supplier_article', 'TEXT')


async def _migrate_product_barcode(db):
    await _migrate_add_column_safe(db, 'product_data', 'barcode', 'TEXT')


async def _migrate_product_wb_metrics(db):
    """Доп. метрики WB для блока «Предложение WB» на листе «Поставки»."""
    await _migrate_add_column_safe(db, 'product_data', 'availability', 'TEXT')
    await _migrate_add_column_safe(db, 'product_data', 'sale_rate_days', 'REAL DEFAULT 0')
    await _migrate_add_column_safe(db, 'product_data', 'office_missing_days', 'REAL DEFAULT 0')
    await _migrate_add_column_safe(db, 'product_data', 'lost_orders', 'REAL DEFAULT 0')
    await _migrate_add_column_safe(db, 'product_data', 'trend_pct', 'REAL DEFAULT 0')


async def _migrate_cache_meta(db):
    """Таблица метаданных кеша: один timestamp на снимок вместо fetched_at в каждой строке."""
    await db.execute('''
        CREATE TABLE IF NOT EXISTS cache_meta (
            store_id INTEGER NOT NULL,
            data_type TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (store_id, data_type)
        )
    ''')
    # Очищаем старые накопленные снимки — оставляем только последний для каждого store_id
    for table in ('product_data', 'warehouse_stocks'):
        await db.execute(f'''
            DELETE FROM {table} WHERE rowid NOT IN (
                SELECT rowid FROM {table} AS t
                WHERE t.fetched_at = (
                    SELECT MAX(t2.fetched_at) FROM {table} AS t2
                    WHERE t2.store_id = t.store_id
                )
            )
        ''')
    # Заполняем cache_meta из существующих данных
    await db.execute('''
        INSERT OR IGNORE INTO cache_meta (store_id, data_type, fetched_at)
        SELECT store_id, 'product', MAX(fetched_at) FROM product_data GROUP BY store_id
    ''')
    await db.execute('''
        INSERT OR IGNORE INTO cache_meta (store_id, data_type, fetched_at)
        SELECT store_id, 'warehouse', MAX(fetched_at) FROM warehouse_stocks GROUP BY store_id
    ''')


async def _migrate_warehouse_id_region(db):
    """Добавляем warehouse_id (канонический ключ WB) и region_name в warehouse_stocks."""
    await _migrate_add_column_safe(db, 'warehouse_stocks', 'warehouse_id', 'INTEGER')
    await _migrate_add_column_safe(db, 'warehouse_stocks', 'region_name', 'TEXT')
    await db.execute('''
        CREATE INDEX IF NOT EXISTS idx_warehouse_stocks_wh_id
            ON warehouse_stocks(store_id, warehouse_id)
    ''')


MIGRATIONS = [
    (1, _migrate_marketplace_name),
    (2, _migrate_obfuscate_tokens),
    (3, _migrate_product_price),
    (4, _migrate_warehouse_stocks),
    (5, _migrate_warehouse_in_way),
    (6, _migrate_warehouse_supplier_article),
    (7, _migrate_cache_meta),
    (8, _migrate_product_barcode),
    (9, _migrate_product_wb_metrics),
    (10, _migrate_warehouse_id_region),
]


async def _run_migrations(db):
    """Применяет миграции по порядку, пропуская уже применённые."""
    await db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    cursor = await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    current = (await cursor.fetchone())[0]

    for version, migration in MIGRATIONS:
        if version <= current:
            continue
        try:
            if callable(migration):
                await migration(db)
            else:
                await db.execute(migration)
            await db.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            logger.info(f"Миграция #{version} применена")
        except Exception as e:
            logger.error(f"Миграция #{version} ошибка: {e}")
            raise

    await db.commit()


async def init_db():
    """Создаёт таблицы если не существуют. Автомигрирует WB_TOKEN из env."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = ON')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                name TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                is_active INTEGER DEFAULT 1
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS report_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER REFERENCES stores(id),
                file_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                subscribed_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS authorized_users (
                chat_id INTEGER PRIMARY KEY,
                authorized_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS product_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER REFERENCES stores(id),
                nm_id INTEGER NOT NULL,
                supplier_article TEXT,
                subject TEXT,
                category TEXT,
                product_group TEXT,
                stock_qty INTEGER,
                in_way_from_client INTEGER DEFAULT 0,
                stock_qty_clean INTEGER,
                orders_7d INTEGER,
                orders_14d INTEGER,
                orders_30d INTEGER,
                avg_per_day REAL,
                days_remaining REAL,
                price_increase_pct INTEGER,
                fetched_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_product_data_store_date
                ON product_data(store_id, fetched_at)
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        await db.commit()

        # Применить миграции
        await _run_migrations(db)

    # Автомиграция: если stores пуста и WB_TOKEN есть в env — добавляем
    # Ленивый импорт для избежания циклических зависимостей
    from bot.db.stores import add_store, get_stores
    from bot.db.subscribers import add_subscriber, get_subscribers

    wb_token = os.getenv('WB_TOKEN')
    if wb_token:
        stores = await get_stores()
        if not stores:
            logger.info("Автомиграция: добавляю магазин из WB_TOKEN...")
            try:
                from bot.services.wb_client import get_seller_info
                info = get_seller_info(wb_token)
                name = info.get('name', 'Магазин 1') if info else 'Магазин 1'
            except Exception:
                name = 'Магазин 1'
            await add_store(wb_token, name)
            logger.info(f"Автомиграция: магазин '{name}' добавлен")

    # Автомиграция: если subscribers пуста и CHAT_ID есть в env — добавляем
    chat_id_env = os.getenv('CHAT_ID')
    if chat_id_env:
        try:
            chat_id = int(chat_id_env)
            subs = await get_subscribers()
            if not subs:
                await add_subscriber(chat_id)
                logger.info(f"Автомиграция: подписчик {chat_id} добавлен из CHAT_ID")
        except (ValueError, Exception) as e:
            logger.warning(f"Автомиграция CHAT_ID не удалась: {e}")


async def migrate_trademarks():
    """Заполняет marketplace_name из WB API для магазинов где оно не задано."""
    import asyncio
    from bot.db.stores import get_stores, update_store

    stores = await get_stores()
    missing = [s for s in stores if not s.get('marketplace_name')]
    if not missing:
        return
    logger.info(f"Загружаю tradeMark для {len(missing)} магазинов...")
    try:
        from bot.services.wb_client import get_seller_info
    except ImportError:
        return
    for store in missing:
        try:
            info = await asyncio.to_thread(get_seller_info, store['token'])
            trade_mark = info.get('tradeMark') if info else None
            if trade_mark:
                await update_store(store['id'], marketplace_name=trade_mark)
                logger.info(f"Магазин #{store['id']}: tradeMark = {trade_mark!r}")
        except Exception as e:
            logger.warning(f"Магазин #{store['id']}: не удалось получить tradeMark: {e}")
