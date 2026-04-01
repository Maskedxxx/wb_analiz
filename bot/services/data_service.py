"""
Загрузка данных из WB API и кэширование через SQLite.

Единственная точка входа для получения данных товаров и складов.
"""

import asyncio
import logging

import pandas as pd

from bot.services.wb_client import (
    get_orders_multi, get_stocks, get_stocks_detailed, get_prices, get_catalog,
    _fetch_raw_stocks, get_stocks_report,
)
from bot.services.calculations import (
    assign_group, calc_days_remaining, get_price_increase,
    merge_orders_stocks,
)
from bot.config import THRESHOLD_A, THRESHOLD_B, THRESHOLD_C, DATA_CACHE_TTL
from bot.db import (
    is_data_fresh, get_latest_product_data, save_product_data,
    is_warehouse_data_fresh, get_latest_warehouse_data, save_warehouse_data,
)

logger = logging.getLogger(__name__)


# ── Загрузка данных из API ────────────────────────────────────────────────────

def fetch_store_data(
    token: str = None,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
    threshold_c: float = THRESHOLD_C,
) -> list[dict]:
    """
    Загружает данные из WB API, рассчитывает метрики.

    Returns:
        Список словарей — по одному на каждый товар (nm_id).
    """
    logger.info("=== Загрузка данных из WB API ===")

    # === 1. Каталог — полный список товаров через Content API ===
    try:
        logger.info("Загрузка каталога (Content API)...")
        catalog = get_catalog(token=token)
        logger.info(f"✓ Каталог: {len(catalog)} карточек")
    except Exception as e:
        logger.warning(f"Content API недоступен: {e}. Fallback на prices_map.")
        catalog = None  # заполним после загрузки цен

    # === 2. Цены ===
    try:
        logger.info("Загрузка цен...")
        prices_map, prices_articles = get_prices(nm_ids=None, token=token)
        logger.info(f"✓ Цены: {len(prices_map)} товаров")
    except Exception as e:
        logger.warning(f"Не удалось загрузить цены: {e}")
        prices_map = {}
        prices_articles = {}

    # Fallback: если каталог не загрузился, используем prices_map как источник ID
    if catalog is None:
        catalog = {nm: {} for nm in prices_map}

    # === 3-4. Остатки + Заказы ===
    # Основной источник: Stocks Report API (замена deprecated Statistics API)
    # Fallback: legacy Statistics Stocks + Orders (на случай недоступности)
    try:
        logger.info("Загрузка остатков и заказов (Stocks Report API)...")
        stocks, orders = get_stocks_report(token=token)
        logger.info(f"✓ Stocks Report: {len(stocks)} товаров")
    except Exception as e:
        logger.warning(f"Stocks Report недоступен: {e}. Fallback на legacy API.")
        try:
            logger.info("Загрузка остатков (legacy)...")
            raw_stocks = _fetch_raw_stocks(nm_ids=None, token=token)
            stocks = get_stocks(_raw_df=raw_stocks)
            logger.info(f"✓ Остатки: {len(stocks)} товаров")
        except Exception as e2:
            logger.error(f"✗ Ошибка загрузки остатков: {e2}")
            raise
        try:
            logger.info("Загрузка заказов за 14 дней (legacy)...")
            orders = get_orders_multi(token=token)
            logger.info(f"✓ Заказы: {len(orders)} товаров с заказами")
        except Exception as e2:
            logger.error(f"✗ Ошибка загрузки заказов: {e2}")
            raise

    # === 5. OUTER JOIN: stocks + orders ===
    df = merge_orders_stocks(orders, stocks)

    # Заполняем поля возвратов если отсутствуют после merge
    for col in ['in_way_from_client', 'stock_qty_clean']:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    # Используем чистый остаток (без товаров в возврате) для расчётов
    df['stock_qty_original'] = df['stock_qty']
    df['stock_qty'] = df['stock_qty_clean']

    # === 6. Восстановление товаров из каталога ∪ prices_map ===
    existing_nm_ids = set(df['nmId'].tolist())
    all_known_ids = set(catalog.keys()) | set(prices_map.keys())
    missing_nm_ids = [nm for nm in all_known_ids if nm not in existing_nm_ids]
    if missing_nm_ids:
        logger.info(f"Добавлено из catalog ∪ prices_map (0 остаток, 0 заказов): {len(missing_nm_ids)}")
        missing_df = pd.DataFrame({'nmId': missing_nm_ids})
        for col in ['stock_qty', 'stock_qty_original', 'in_way_from_client', 'stock_qty_clean',
                     'orders_count_7d', 'orders_count_14d']:
            missing_df[col] = 0
        missing_df['supplierArticle'] = missing_df['nmId'].map(
            lambda nm: catalog.get(nm, {}).get('supplierArticle', ''))
        missing_df['subject'] = missing_df['nmId'].map(
            lambda nm: catalog.get(nm, {}).get('subject', ''))
        missing_df['category'] = missing_df['nmId'].map(
            lambda nm: catalog.get(nm, {}).get('category', ''))
        df = pd.concat([df, missing_df], ignore_index=True)

    # === 7. Обогащение метаданных из каталога для всех товаров ===
    for col in ['supplierArticle', 'subject', 'category']:
        mask = df[col].isna() | (df[col] == '')
        if mask.any():
            df.loc[mask, col] = df.loc[mask, 'nmId'].map(
                lambda nm: catalog.get(nm, {}).get(col, ''))

    # === 7b. Fallback артикулов из Prices API (для товаров не в каталоге) ===
    mask = df['supplierArticle'].isna() | (df['supplierArticle'] == '')
    if mask.any():
        df.loc[mask, 'supplierArticle'] = df.loc[mask, 'nmId'].map(
            lambda nm: prices_articles.get(nm, ''))

    logger.info(f"Всего товаров в каталоге: {len(df)}")

    # === 5. Группировка A/B/C по среднему за 14д ===
    # Если avg_per_day уже пришёл из Stocks Report API — используем его,
    # иначе считаем вручную (legacy fallback)
    if 'avg_per_day' not in df.columns or df['avg_per_day'].isna().all():
        df['avg_per_day'] = df['orders_count_14d'] / 14
    else:
        df['avg_per_day'] = df['avg_per_day'].fillna(df['orders_count_14d'] / 14)
    df['group'] = df['avg_per_day'].apply(lambda x: assign_group(x, threshold_a, threshold_b, threshold_c))

    # === 6. Расчёт days_remaining ===
    df['days_remaining'] = df.apply(calc_days_remaining, axis=1)

    # === 7. Расчёт % повышения цены ===
    df['price_increase_pct'] = df['days_remaining'].apply(lambda d: get_price_increase(d, days_threshold))

    # === 8. Маппинг цен ===
    df['price'] = df['nmId'].map(prices_map)

    logger.info("=== Данные загружены и рассчитаны ===")

    # Конвертируем в list[dict] для сохранения в БД
    result = []
    for _, row in df.iterrows():
        result.append({
            'nm_id': int(row['nmId']),
            'supplier_article': row.get('supplierArticle'),
            'subject': row.get('subject'),
            'category': row.get('category'),
            'product_group': row['group'],
            'stock_qty': int(row['stock_qty']),
            'in_way_from_client': int(row['in_way_from_client']),
            'stock_qty_clean': int(row['stock_qty_clean']),
            'orders_7d': int(row['orders_count_7d']) if pd.notna(row.get('orders_count_7d')) else None,
            'orders_14d': int(row['orders_count_14d']) if pd.notna(row.get('orders_count_14d')) else None,
            'orders_30d': None,  # больше не запрашивается, колонка сохранена для совместимости БД
            'avg_per_day': round(row['avg_per_day'], 4),
            'days_remaining': round(row['days_remaining'], 2) if row['days_remaining'] is not None else None,
            'price_increase_pct': int(row['price_increase_pct']),
            'price': float(row['price']) if pd.notna(row.get('price')) else None,
        })

    return result


def fetch_warehouse_data(token: str, nm_ids: list = None, _raw_df=None) -> list[dict]:
    """
    Загружает детализацию остатков по складам из WB API.

    Args:
        _raw_df: предзагруженные сырые данные (для устранения дублирования запросов)

    Returns:
        Список словарей {nm_id, warehouse_name, quantity}
    """
    df = get_stocks_detailed(nm_ids=nm_ids, token=token, _raw_df=_raw_df)
    if df.empty:
        return []
    return [
        {
            'nm_id': int(row['nmId']),
            'warehouse_name': row['warehouseName'],
            'quantity': int(row['quantity']),
            'in_way_from_client': int(row.get('inWayFromClient', 0)),
            'supplier_article': row.get('supplierArticle') or None,
        }
        for _, row in df.iterrows()
    ]


# ── Кэширование ──────────────────────────────────────────────────────────────

async def fetch_or_cache_product(store_id, token, days_threshold, threshold_a, threshold_b):
    """Загружает данные товаров из кэша или API."""
    if await is_data_fresh(store_id, DATA_CACHE_TTL):
        rows, _ = await get_latest_product_data(store_id)
        return rows
    rows = await asyncio.to_thread(
        fetch_store_data, token=token,
        days_threshold=days_threshold,
        threshold_a=threshold_a,
        threshold_b=threshold_b,
    )
    await save_product_data(store_id, rows)
    return rows


async def fetch_or_cache_warehouse(store_id, token):
    """Загружает данные по складам из кэша или API."""
    if await is_warehouse_data_fresh(store_id, DATA_CACHE_TTL):
        wh_data = await get_latest_warehouse_data(store_id)
        if wh_data:
            return wh_data
    wh_data = await asyncio.to_thread(fetch_warehouse_data, token=token)
    await save_warehouse_data(store_id, wh_data)
    return wh_data
