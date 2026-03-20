"""
Модуль работы с SQLite: магазины, настройки, история отчётов, подписчики.
"""

import os
import time
import logging
import aiosqlite

from bot.security import obfuscate_token, deobfuscate_token

logger = logging.getLogger(__name__)

DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'bot.db'))


# === Миграции БД ===
# Каждая миграция — (версия, SQL или async-функция).
# SQL выполняется напрямую; функция вызывается с аргументом db (aiosqlite.Connection).

async def _migrate_obfuscate_tokens(db):
    """Обфусцирует plaintext-токены (без префикса 'obf:')."""
    cursor = await db.execute("SELECT id, token FROM stores WHERE token NOT LIKE 'obf:%'")
    plain_rows = await cursor.fetchall()
    for row_id, raw_token in plain_rows:
        await db.execute('UPDATE stores SET token = ? WHERE id = ?', (obfuscate_token(raw_token), row_id))
    if plain_rows:
        logger.info(f"Обфусцировано токенов: {len(plain_rows)}")


async def _migrate_add_column_safe(db, table, column, col_type):
    """Добавляет колонку если её ещё нет (идемпотентно)."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in await cursor.fetchall()]
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


async def _migrate_marketplace_name(db):
    await _migrate_add_column_safe(db, 'stores', 'marketplace_name', 'TEXT')


async def _migrate_product_price(db):
    await _migrate_add_column_safe(db, 'product_data', 'price', 'REAL')


MIGRATIONS = [
    (1, _migrate_marketplace_name),
    (2, _migrate_obfuscate_tokens),
    (3, _migrate_product_price),
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


async def _connect():
    """Подключение к БД с включёнными foreign keys."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute('PRAGMA foreign_keys = ON')
    return db


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
    wb_token = os.getenv('WB_TOKEN')
    if wb_token:
        stores = await get_stores()
        if not stores:
            logger.info("Автомиграция: добавляю магазин из WB_TOKEN...")
            try:
                from wb_api import get_seller_info
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
    stores = await get_stores()
    missing = [s for s in stores if not s.get('marketplace_name')]
    if not missing:
        return
    logger.info(f"Загружаю tradeMark для {len(missing)} магазинов...")
    try:
        from wb_api import get_seller_info
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


# === Stores CRUD ===

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


# === Settings ===

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


# === Report History ===

async def save_report_history(store_id: int, file_path: str) -> int:
    """Сохраняет запись об отчёте. Возвращает id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO report_history (store_id, file_path) VALUES (?, ?)',
            (store_id, file_path)
        )
        await db.commit()
        return cursor.lastrowid


async def get_last_report(store_id: int) -> dict | None:
    """Возвращает последний отчёт для магазина."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT id, store_id, file_path, created_at FROM report_history '
            'WHERE store_id = ? ORDER BY created_at DESC LIMIT 1',
            (store_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def cleanup_old_reports(days: int) -> int:
    """Удаляет отчёты старше days дней из БД и с диска. Возвращает кол-во удалённых."""
    import asyncio

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, file_path FROM report_history "
            "WHERE created_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        rows = await cursor.fetchall()

        deleted = 0
        for row in rows:
            fp = row['file_path']
            if fp and await asyncio.to_thread(os.path.exists, fp):
                await asyncio.to_thread(os.remove, fp)
            await db.execute('DELETE FROM report_history WHERE id = ?', (row['id'],))
            deleted += 1

        await db.commit()
    return deleted


# === Subscribers ===

async def add_subscriber(chat_id: int):
    """Добавляет подписчика на ежедневные отчёты."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)',
            (chat_id,)
        )
        await db.commit()


async def remove_subscriber(chat_id: int):
    """Удаляет подписчика."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'DELETE FROM subscribers WHERE chat_id = ?',
            (chat_id,)
        )
        await db.commit()


async def get_subscribers() -> list[int]:
    """Возвращает список chat_id всех подписчиков."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT chat_id FROM subscribers')
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def is_subscriber(chat_id: int) -> bool:
    """Проверяет, подписан ли пользователь."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT 1 FROM subscribers WHERE chat_id = ?',
            (chat_id,)
        )
        return await cursor.fetchone() is not None


# === Authorization (с in-memory кэшем) ===

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
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT chat_id FROM authorized_users')
        rows = await cursor.fetchall()
        _authorized_cache.clear()
        _authorized_cache.update(row[0] for row in rows)
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


# === Product Data (кэш API-данных) ===

async def save_product_data(store_id: int, rows: list[dict]):
    """
    Сохраняет снимок данных по товарам магазина.

    Args:
        store_id: ID магазина
        rows: список словарей с полями товара
    """
    async with aiosqlite.connect(DB_PATH) as db:
        for row in rows:
            await db.execute(
                '''INSERT INTO product_data
                   (store_id, nm_id, supplier_article, subject, category,
                    product_group, stock_qty, in_way_from_client, stock_qty_clean,
                    orders_7d, orders_14d, orders_30d,
                    avg_per_day, days_remaining, price_increase_pct, price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (store_id, row['nm_id'], row.get('supplier_article'),
                 row.get('subject'), row.get('category'),
                 row.get('product_group'), row.get('stock_qty'),
                 row.get('in_way_from_client', 0), row.get('stock_qty_clean'),
                 row.get('orders_7d'), row.get('orders_14d'), row.get('orders_30d'),
                 row.get('avg_per_day'), row.get('days_remaining'),
                 row.get('price_increase_pct'), row.get('price'))
            )
        await db.commit()


async def get_latest_product_data(store_id: int) -> tuple[list[dict], str | None]:
    """
    Возвращает последний снимок данных по магазину.

    Returns:
        (rows, fetched_at) — список товаров и время загрузки, или ([], None)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Находим время последнего снимка
        cursor = await db.execute(
            'SELECT fetched_at FROM product_data WHERE store_id = ? '
            'ORDER BY fetched_at DESC LIMIT 1',
            (store_id,)
        )
        ts_row = await cursor.fetchone()
        if not ts_row:
            return [], None

        fetched_at = ts_row[0]

        # Забираем все строки этого снимка
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM product_data WHERE store_id = ? AND fetched_at = ?',
            (store_id, fetched_at)
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return rows, fetched_at


async def is_data_fresh(store_id: int, ttl_minutes: int) -> bool:
    """Проверяет, есть ли данные свежее ttl_minutes минут."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM product_data WHERE store_id = ? "
            "AND fetched_at > datetime('now', ?)"
            " LIMIT 1",
            (store_id, f'-{ttl_minutes} minutes')
        )
        return await cursor.fetchone() is not None


async def cleanup_old_product_data(days: int) -> int:
    """Удаляет данные о товарах старше days дней. Возвращает кол-во удалённых."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM product_data WHERE fetched_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        await db.commit()
        return cursor.rowcount


# === Audit Log ===

async def log_action(chat_id: int, action: str, details: str = None):
    """Записывает действие в аудит-лог."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO audit_log (chat_id, action, details) VALUES (?, ?, ?)',
            (chat_id, action, details)
        )
        await db.commit()
