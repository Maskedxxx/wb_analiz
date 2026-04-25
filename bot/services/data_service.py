"""
Загрузка данных из WB API и кэширование через SQLite.

Единственная точка входа для получения данных товаров и складов.
"""

import asyncio
import logging

import pandas as pd

from bot.services.wb_client import (
    get_prices, get_catalog, get_stocks_report, get_warehouse_stocks,
)
from bot.services.calculations import (
    assign_group, calc_days_remaining, get_price_increase,
    merge_orders_stocks,
)
from bot.config import THRESHOLD_A, THRESHOLD_B, THRESHOLD_C, DATA_CACHE_TTL, FORCE_REFRESH
from bot.db import (
    is_data_fresh, get_latest_product_data, save_product_data,
    is_warehouse_data_fresh, get_latest_warehouse_data, save_warehouse_data,
)

logger = logging.getLogger(__name__)


def _fetch_raw_data(token: str):
    """Загружает сырые данные из WB API: каталог, цены, стоки."""
    catalog_ok = False
    try:
        logger.info("Загрузка каталога (Content API)...")
        catalog = get_catalog(token=token)
        catalog_ok = True
        logger.info(f"✓ Каталог: {len(catalog)} карточек")
    except Exception as e:
        logger.warning(f"Content API недоступен: {e}. Fallback на prices_map.")
        catalog = None

    try:
        logger.info("Загрузка цен...")
        prices_map, prices_articles, prices_barcodes = get_prices(nm_ids=None, token=token)
        logger.info(f"✓ Цены: {len(prices_map)} товаров")
    except Exception as e:
        logger.warning(f"Не удалось загрузить цены: {e}")
        prices_map = {}
        prices_articles = {}
        prices_barcodes = {}

    if catalog is None:
        catalog = {nm: {} for nm in prices_map}

    logger.info("Загрузка остатков и заказов (Stocks Report API)...")
    stocks, orders = get_stocks_report(token=token)
    logger.info(f"✓ Stocks Report: {len(stocks)} товаров")

    return catalog, catalog_ok, prices_map, prices_articles, prices_barcodes, stocks, orders


def _enrich_metadata(df, catalog, catalog_ok, prices_map, prices_articles, prices_barcodes):
    """Обогащает DataFrame метаданными: каталог, баркоды, артикулы."""
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
        missing_df['barcode'] = missing_df['nmId'].map(
            lambda nm: catalog.get(nm, {}).get('barcode', ''))
        df = pd.concat([df, missing_df], ignore_index=True)

    for col in ['supplierArticle', 'subject', 'category']:
        mask = df[col].isna() | (df[col] == '')
        if mask.any():
            df.loc[mask, col] = df.loc[mask, 'nmId'].map(
                lambda nm: catalog.get(nm, {}).get(col, ''))

    if 'barcode' not in df.columns:
        df['barcode'] = ''
    df['barcode'] = df['barcode'].fillna('')
    mask = df['barcode'] == ''
    if mask.any() and catalog_ok:
        df.loc[mask, 'barcode'] = df.loc[mask, 'nmId'].map(
            lambda nm: catalog.get(nm, {}).get('barcode', ''))
        df['barcode'] = df['barcode'].fillna('')
        filled = (df['barcode'] != '').sum()
        logger.info(f"Баркоды из каталога: {filled}/{len(df)}")

    mask = df['barcode'] == ''
    if mask.any() and prices_barcodes:
        df.loc[mask, 'barcode'] = df.loc[mask, 'nmId'].map(
            lambda nm: prices_barcodes.get(nm, ''))
        df['barcode'] = df['barcode'].fillna('')
        still_empty = (df['barcode'] == '').sum()
        if still_empty:
            logger.warning(f"Баркоды: {still_empty} товаров без баркода после всех fallback")

    mask = df['supplierArticle'].isna() | (df['supplierArticle'] == '')
    if mask.any():
        df.loc[mask, 'supplierArticle'] = df.loc[mask, 'nmId'].map(
            lambda nm: prices_articles.get(nm, ''))

    logger.info(f"Всего товаров в каталоге: {len(df)}")
    return df


def _calculate_metrics(df, days_threshold, threshold_a, threshold_b, threshold_c):
    """Рассчитывает группы, days_remaining, price_increase."""
    if 'avg_per_day' not in df.columns or df['avg_per_day'].isna().all():
        df['avg_per_day'] = df['orders_count_14d'] / 14
    else:
        df['avg_per_day'] = df['avg_per_day'].fillna(df['orders_count_14d'] / 14)
    df['group'] = df['avg_per_day'].apply(lambda x: assign_group(x, threshold_a, threshold_b, threshold_c))
    df['days_remaining'] = df.apply(calc_days_remaining, axis=1)
    df['price_increase_pct'] = df['days_remaining'].apply(lambda d: get_price_increase(d, days_threshold))
    return df


def _to_dicts(df, metrics_index, prices_map):
    """Конвертирует DataFrame в list[dict] для сохранения в БД."""
    result = []
    for _, row in df.iterrows():
        nm_id = int(row['nmId'])
        m = metrics_index.get(nm_id, {})
        result.append({
            'nm_id': nm_id,
            'supplier_article': row.get('supplierArticle'),
            'subject': row.get('subject'),
            'category': row.get('category'),
            'product_group': row['group'],
            'stock_qty': int(row['stock_qty']),
            'in_way_from_client': int(row['in_way_from_client']),
            'stock_qty_clean': int(row['stock_qty_clean']),
            'orders_7d': int(row['orders_count_7d']) if pd.notna(row.get('orders_count_7d')) else None,
            'orders_14d': int(row['orders_count_14d']) if pd.notna(row.get('orders_count_14d')) else None,
            'orders_30d': None,
            'avg_per_day': round(row['avg_per_day'], 4),
            'days_remaining': round(row['days_remaining'], 2) if row['days_remaining'] is not None else None,
            'price_increase_pct': int(row['price_increase_pct']),
            'price': float(row['price']) if pd.notna(row.get('price')) else None,
            'barcode': row.get('barcode') if pd.notna(row.get('barcode')) else '',
            'availability': (m.get('availability') or '') if m else '',
            'sale_rate_days': float(m.get('sale_rate_days') or 0) if m else 0.0,
            'office_missing_days': float(m.get('office_missing_days') or 0) if m else 0.0,
            'lost_orders': float(m.get('lost_orders') or 0) if m else 0.0,
            'trend_pct': float(m.get('trend_pct') or 0) if m else 0.0,
        })
    return result


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

    catalog, catalog_ok, prices_map, prices_articles, prices_barcodes, stocks, orders = _fetch_raw_data(token)

    metrics_index = {}
    if not orders.empty:
        metric_cols = ('availability', 'sale_rate_days', 'office_missing_days',
                       'lost_orders', 'trend_pct')
        present = [c for c in metric_cols if c in orders.columns]
        if present:
            for _, r in orders.iterrows():
                metrics_index[int(r['nmId'])] = {c: r.get(c) for c in present}

    df = merge_orders_stocks(orders, stocks)

    for col in ['in_way_from_client', 'stock_qty_clean']:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    df['stock_qty_original'] = df['stock_qty']
    df['stock_qty'] = df['stock_qty_clean']

    df = _enrich_metadata(df, catalog, catalog_ok, prices_map, prices_articles, prices_barcodes)
    df = _calculate_metrics(df, days_threshold, threshold_a, threshold_b, threshold_c)
    df['price'] = df['nmId'].map(prices_map)

    logger.info("=== Данные загружены и рассчитаны ===")

    return _to_dicts(df, metrics_index, prices_map)


def fetch_warehouse_data(token: str, nm_ids: list = None) -> list[dict]:
    """
    Загружает детализацию остатков по складам из WB API (wb-warehouses).

    Returns:
        Список словарей {nm_id, warehouse_name, quantity, in_way_from_client}
    """
    df = get_warehouse_stocks(token=token, nm_ids=nm_ids)
    if df.empty:
        return []
    return [
        {
            'nm_id': int(row['nmId']),
            'warehouse_id': int(row['warehouseId']) if row.get('warehouseId') else None,
            'warehouse_name': row['warehouseName'],
            'region_name': row.get('regionName', ''),
            'quantity': int(row['quantity']),
            'in_way_from_client': int(row.get('inWayFromClient', 0)),
            'supplier_article': '',
        }
        for _, row in df.iterrows()
    ]


async def fetch_or_cache_product(store_id, token, days_threshold, threshold_a, threshold_b,
                                 force_refresh=FORCE_REFRESH):
    """Загружает данные товаров из кэша или API."""
    if not force_refresh and await is_data_fresh(store_id, DATA_CACHE_TTL):
        rows, _ = await get_latest_product_data(store_id)
        has_barcodes = any(r.get('barcode') for r in rows) if rows else False
        has_wb_metrics = any('availability' in r for r in rows) if rows else False
        if rows and has_barcodes and has_wb_metrics:
            return rows
        logger.info("Кэш без баркодов или WB-метрик — принудительная перезагрузка")
    rows = await asyncio.to_thread(
        fetch_store_data, token=token,
        days_threshold=days_threshold,
        threshold_a=threshold_a,
        threshold_b=threshold_b,
    )
    await save_product_data(store_id, rows)
    return rows


async def fetch_or_cache_warehouse(store_id, token, force_refresh=FORCE_REFRESH):
    """Загружает данные по складам из кэша или API."""
    if not force_refresh and await is_warehouse_data_fresh(store_id, DATA_CACHE_TTL):
        wh_data = await get_latest_warehouse_data(store_id)
        if wh_data:
            return wh_data
    wh_data = await asyncio.to_thread(fetch_warehouse_data, token=token)
    await save_warehouse_data(store_id, wh_data)
    return wh_data
