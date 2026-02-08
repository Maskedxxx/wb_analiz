"""
Функции для работы с WB API.
"""

import json
import logging
import time
import urllib.request
from datetime import datetime, timedelta
from http.client import IncompleteRead
from urllib.error import URLError

import pandas as pd
import os

logger = logging.getLogger(__name__)

# API endpoints
API_ORDERS = 'https://statistics-api.wildberries.ru/api/v1/supplier/orders'
API_STOCKS = 'https://statistics-api.wildberries.ru/api/v1/supplier/stocks'


def get_token() -> str:
    """Возвращает токен WB API из переменной окружения WB_TOKEN."""
    token = os.getenv('WB_TOKEN')
    if not token:
        raise ValueError("WB_TOKEN не задан в переменных окружения")
    return token


def fetch_with_retry(url: str, token: str, retries: int = 3, delay: int = 5) -> list:
    """
    Выполняет HTTP запрос с повторными попытками при ошибках сети.

    Args:
        url: URL для запроса
        token: токен авторизации
        retries: количество попыток (по умолчанию 3)
        delay: пауза между попытками в секундах (по умолчанию 5)

    Returns:
        Список данных из JSON ответа
    """
    req = urllib.request.Request(url)
    req.add_header('Authorization', token)

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Попытка {attempt}/{retries}...")
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            return data if data else []

        except (IncompleteRead, URLError, TimeoutError) as e:
            logger.warning(f"Попытка {attempt}/{retries} не удалась: {e}")
            if attempt < retries:
                logger.info(f"Ожидание {delay} сек перед повтором...")
                time.sleep(delay)
            else:
                logger.error(f"Все {retries} попытки исчерпаны")
                raise


def calc_avg_per_day(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    """
    Добавляет колонку среднего заказов в день за период.

    Args:
        df: DataFrame с колонкой orders_count_{days}d
        days: период в днях (по умолчанию 7)

    Returns:
        DataFrame с добавленной колонкой avg_per_day_{days}d
    """
    df = df.copy()
    orders_col = f'orders_count_{days}d'
    avg_col = f'avg_per_day_{days}d'
    df[avg_col] = df[orders_col] / days
    return df


def merge_orders_stocks(orders: pd.DataFrame, stocks: pd.DataFrame) -> pd.DataFrame:
    """
    Объединяет заказы и остатки, сортирует по убыванию остатка.

    Args:
        orders: DataFrame с заказами
        stocks: DataFrame с остатками

    Returns:
        DataFrame объединённый, отсортированный по stock_qty (убывание)
    """
    df = orders.merge(stocks, on='nmId', how='left')
    df['stock_qty'] = df['stock_qty'].fillna(0).astype(int)
    df = df.sort_values('stock_qty', ascending=False).reset_index(drop=True)
    return df


def get_stocks(nm_ids: list = None) -> pd.DataFrame:
    """
    Получает остатки со складов, группирует по nmId.

    Args:
        nm_ids: список nmId для фильтрации (если None — все)

    Returns:
        DataFrame с колонками:
        - nmId: ID товара
        - stock_qty: суммарный остаток на всех складах
    """
    token = get_token()
    date_from = '2020-01-01'  # берём все остатки

    url = f"{API_STOCKS}?dateFrom={date_from}"
    data = fetch_with_retry(url, token)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Фильтруем по nm_ids если передан список
    if nm_ids is not None:
        df = df[df['nmId'].isin(nm_ids)]

    # Добавляем поле inWayFromClient (товары в возврате/отказе, в пути на склад)
    if 'inWayFromClient' not in df.columns:
        df['inWayFromClient'] = 0

    # Группируем по nmId, суммируем остатки и возвраты в пути
    grouped = df.groupby('nmId').agg({
        'quantity': 'sum',
        'inWayFromClient': 'sum'
    }).rename(columns={
        'quantity': 'stock_qty',
        'inWayFromClient': 'in_way_from_client'
    }).reset_index()

    # Чистый остаток = остаток на складе минус товары в возврате
    grouped['stock_qty_clean'] = (grouped['stock_qty'] - grouped['in_way_from_client']).clip(lower=0)

    return grouped


def get_orders(days: int = 7) -> pd.DataFrame:
    """
    Получает заказы за N дней и группирует по nmId.

    Args:
        days: количество дней (по умолчанию 7)

    Returns:
        DataFrame с колонками:
        - nmId: ID товара
        - supplierArticle: артикул продавца
        - subject: название товара
        - category: категория
        - orders_count: количество заказов
    """
    token = get_token()
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Запрос к API с retry
    url = f"{API_ORDERS}?dateFrom={date_from}"
    data = fetch_with_retry(url, token)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Группируем по nmId
    col_name = f'orders_count_{days}d'
    grouped = df.groupby('nmId').agg({
        'supplierArticle': 'first',
        'subject': 'first',
        'category': 'first',
        'nmId': 'count'
    }).rename(columns={'nmId': col_name}).reset_index()

    return grouped
