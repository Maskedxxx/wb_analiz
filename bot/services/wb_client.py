"""
HTTP-клиент WB API: авторизация, retry, эндпоинты.
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
API_ORDERS = 'https://statistics-api.wildberries.ru/api/v1/supplier/orders'  # deprecated, удаление 23.06.2025
API_STOCKS = 'https://statistics-api.wildberries.ru/api/v1/supplier/stocks'  # deprecated, удаление 23.06.2025
API_SELLER_INFO = 'https://common-api.wildberries.ru/api/v1/seller-info'
API_PRICES = 'https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter'
API_CONTENT_CARDS = 'https://content-api.wildberries.ru/content/v2/get/cards/list'
API_STOCKS_REPORT = 'https://seller-analytics-api.wildberries.ru/api/v2/stocks-report/products/products'


class WBTokenError(Exception):
    """Ошибка авторизации WB API (невалидный или истёкший токен)."""
    pass


class WBApiError(Exception):
    """Общая ошибка WB API."""
    pass


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

    Raises:
        WBTokenError: при ошибке авторизации (401/403)
        WBApiError: при других HTTP ошибках
    """
    req = urllib.request.Request(url)
    req.add_header('Authorization', token)

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Попытка {attempt}/{retries}...")
            with urllib.request.urlopen(req, timeout=180) as resp:
                chunks = []
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                data = json.loads(b''.join(chunks).decode('utf-8'))
            return data if data else []

        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise WBTokenError(
                    f"Токен невалиден или истёк (HTTP {e.code}). "
                    "Обновите токен в настройках бота."
                )
            if e.code == 429:
                logger.warning(f"Rate limit (429), ожидание {delay * 2} сек...")
                time.sleep(delay * 2)
                continue
            raise WBApiError(f"Ошибка WB API: HTTP {e.code}") from e

        except (IncompleteRead, URLError, TimeoutError) as e:
            logger.warning(f"Попытка {attempt}/{retries} не удалась: {e}")
            if attempt < retries:
                logger.info(f"Ожидание {delay} сек перед повтором...")
                time.sleep(delay)
            else:
                logger.error(f"Все {retries} попытки исчерпаны")
                raise


def post_with_retry(url: str, token: str, body: dict, retries: int = 3, delay: int = 5):
    """
    Выполняет POST запрос с JSON body и повторными попытками.

    Args:
        url: URL для запроса
        token: токен авторизации
        body: тело запроса (будет сериализовано в JSON)
        retries: количество попыток
        delay: пауза между попытками в секундах

    Returns:
        Данные из JSON ответа

    Raises:
        WBTokenError: при ошибке авторизации (401/403)
        WBApiError: при других HTTP ошибках
    """
    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('Authorization', token)
    req.add_header('Content-Type', 'application/json')

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                chunks = []
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                data = json.loads(b''.join(chunks).decode('utf-8'))
            return data if data else {}

        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise WBTokenError(
                    f"Токен невалиден или истёк (HTTP {e.code}). "
                    "Обновите токен в настройках бота."
                )
            if e.code == 429:
                logger.warning(f"Rate limit (429), ожидание {delay * 2} сек...")
                time.sleep(delay * 2)
                continue
            raise WBApiError(f"Ошибка WB API: HTTP {e.code}") from e

        except (IncompleteRead, URLError, TimeoutError) as e:
            logger.warning(f"POST попытка {attempt}/{retries} не удалась: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                logger.error(f"Все {retries} попытки исчерпаны")
                raise


def get_catalog(token: str = None) -> dict:
    """
    Получает полный каталог товаров через Content API (курсорная пагинация).

    Возвращает ВСЕ карточки товаров продавца, включая товары без остатков и продаж.

    Args:
        token: токен WB API

    Returns:
        dict {nmId: {'supplierArticle': str, 'subject': str, 'category': str}}
    """
    if token is None:
        token = get_token()

    catalog = {}
    limit = 100
    cursor = {"limit": limit}

    while True:
        body = {
            "settings": {
                "cursor": cursor,
                "filter": {"withPhoto": -1},
                "sort": {"ascending": False},
            },
        }
        data = post_with_retry(API_CONTENT_CARDS, token, body, retries=2)

        cards = data.get('cards', [])
        if not cards:
            break

        for card in cards:
            nm_id = card.get('nmID')
            if nm_id is None:
                continue
            catalog[nm_id] = {
                'supplierArticle': card.get('vendorCode', ''),
                'subject': card.get('subjectName', ''),
                'category': card.get('subjectName', ''),
            }

        # Курсорная пагинация: берём cursor из ответа
        resp_cursor = data.get('cursor', {})
        total = resp_cursor.get('total', 0)

        if total < limit:
            break

        # Следующая страница
        cursor = {
            "limit": limit,
            "updatedAt": resp_cursor.get('updatedAt', ''),
            "nmID": resp_cursor.get('nmID', 0),
        }

        # Пауза между страницами (лимит 100 req/min)
        time.sleep(0.7)

    logger.info(f"Каталог Content API: {len(catalog)} карточек")
    return catalog


def get_seller_info(token: str) -> dict:
    """
    Получает информацию о продавце по токену.

    Args:
        token: токен WB API

    Returns:
        dict с информацией о продавце (name, sid, etc.)

    Raises:
        WBTokenError: при невалидном токене
    """
    data = fetch_with_retry(API_SELLER_INFO, token, retries=1)
    return data if isinstance(data, dict) else {}


def _fetch_raw_stocks(nm_ids: list = None, token: str = None) -> pd.DataFrame:
    """
    Загружает сырые данные остатков из API (один HTTP-запрос).

    Используется как общий источник для get_stocks() и get_stocks_detailed().
    """
    if token is None:
        token = get_token()
    date_from = '2020-01-01'

    url = f"{API_STOCKS}?dateFrom={date_from}"
    data = fetch_with_retry(url, token)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    if nm_ids is not None:
        df = df[df['nmId'].isin(nm_ids)]

    if 'inWayFromClient' not in df.columns:
        df['inWayFromClient'] = 0

    for col in ['supplierArticle', 'subject', 'category', 'warehouseName']:
        if col not in df.columns:
            df[col] = ''

    return df


def get_stocks(nm_ids: list = None, token: str = None, _raw_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Получает остатки со складов, группирует по nmId.

    Args:
        nm_ids: список nmId для фильтрации (если None — все)
        token: токен WB API (если None — из переменной окружения)
        _raw_df: предзагруженные сырые данные (для устранения дублирования запросов)

    Returns:
        DataFrame с колонками:
        - nmId: ID товара
        - stock_qty: суммарный остаток на всех складах
        - in_way_from_client: товары в возврате
        - stock_qty_clean: чистый остаток
    """
    df = _raw_df if _raw_df is not None else _fetch_raw_stocks(nm_ids, token)

    if df.empty:
        return pd.DataFrame()

    # Группируем по nmId, суммируем остатки и возвраты в пути
    grouped = df.groupby('nmId').agg({
        'quantity': 'sum',
        'inWayFromClient': 'sum',
        'supplierArticle': 'first',
        'subject': 'first',
        'category': 'first',
    }).rename(columns={
        'quantity': 'stock_qty',
        'inWayFromClient': 'in_way_from_client'
    }).reset_index()

    # Чистый остаток = остаток на складе минус товары в возврате
    grouped['stock_qty_clean'] = (grouped['stock_qty'] - grouped['in_way_from_client']).clip(lower=0)

    return grouped


def get_stocks_detailed(nm_ids: list = None, token: str = None, _raw_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Получает остатки по складам БЕЗ группировки — сохраняет детализацию по каждому складу.

    Args:
        nm_ids: список nmId для фильтрации (если None — все)
        token: токен WB API (если None — из переменной окружения)
        _raw_df: предзагруженные сырые данные (для устранения дублирования запросов)

    Returns:
        DataFrame с колонками:
        - nmId: ID товара
        - warehouseName: название склада
        - quantity: остаток на складе
        - inWayFromClient: товары в возврате
    """
    df = _raw_df if _raw_df is not None else _fetch_raw_stocks(nm_ids, token)

    if df.empty:
        return pd.DataFrame(columns=['nmId', 'warehouseName', 'quantity', 'inWayFromClient'])

    # Сохраняем только нужные колонки, не группируем
    cols = ['nmId', 'warehouseName', 'quantity', 'inWayFromClient', 'supplierArticle']
    for c in cols:
        if c not in df.columns:
            df[c] = '' if c in ('warehouseName', 'supplierArticle') else 0

    return df[cols].reset_index(drop=True)


def get_prices(nm_ids: list = None, token: str = None) -> tuple[dict, dict]:
    """
    Получает цены товаров (после скидки) через Prices API.

    Args:
        nm_ids: список nmId для фильтрации (если None — все)
        token: токен WB API

    Returns:
        tuple (prices, articles):
            prices: dict {nmID: discountedPrice} — минимальная цена среди размеров
            articles: dict {nmID: vendorCode} — артикулы продавца
    """
    if token is None:
        token = get_token()

    nm_set = set(nm_ids) if nm_ids else None
    prices = {}
    articles = {}
    limit = 1000
    offset = 0

    while True:
        url = f"{API_PRICES}?limit={limit}&offset={offset}"
        data = fetch_with_retry(url, token, retries=2)

        if not data:
            break

        goods = data.get('data', {}).get('listGoods', [])
        if not goods:
            break

        for item in goods:
            nm_id = item.get('nmID')
            if nm_set is not None and nm_id not in nm_set:
                continue
            articles[nm_id] = item.get('vendorCode', '')
            sizes = item.get('sizes', [])
            if sizes:
                discounted = [s.get('discountedPrice') for s in sizes
                              if s.get('discountedPrice') is not None]
                prices[nm_id] = min(discounted) if discounted else 0
            else:
                prices[nm_id] = 0

        if len(goods) < limit:
            break
        offset += limit

    logger.info(f"Загружено цен: {len(prices)}")
    return prices, articles


def get_orders(days: int = 7, token: str = None) -> pd.DataFrame:
    """
    Получает заказы за N дней и группирует по nmId.

    Args:
        days: количество дней (по умолчанию 7)
        token: токен WB API (если None — из переменной окружения)

    Returns:
        DataFrame с колонками:
        - nmId: ID товара
        - supplierArticle: артикул продавца
        - subject: название товара
        - category: категория
        - orders_count_{days}d: количество заказов
    """
    if token is None:
        token = get_token()
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Запрос к API с retry
    url = f"{API_ORDERS}?dateFrom={date_from}"
    data = fetch_with_retry(url, token)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Исключаем отменённые заказы (isCancel=True)
    if 'isCancel' in df.columns:
        df = df[df['isCancel'] != True]

    # Группируем по nmId
    col_name = f'orders_count_{days}d'
    grouped = df.groupby('nmId').agg({
        'supplierArticle': 'first',
        'subject': 'first',
        'category': 'first',
        'nmId': 'count'
    }).rename(columns={'nmId': col_name}).reset_index()

    return grouped


def get_orders_multi(token: str = None) -> pd.DataFrame:
    """
    Оптимизированная загрузка: 1 запрос за 14 дней, из него вычисляются 7д и 14д.
    Заменяет 3 отдельных вызова get_orders(30/14/7).

    Returns:
        DataFrame с колонками: nmId, supplierArticle, subject, category,
        orders_count_7d, orders_count_14d
    """
    if token is None:
        token = get_token()

    # Один запрос за 14 дней — покрывает и 7д как подмножество
    date_from_14 = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    date_from_7 = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    url = f"{API_ORDERS}?dateFrom={date_from_14}"
    data = fetch_with_retry(url, token)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Исключаем отменённые заказы
    if 'isCancel' in df.columns:
        df = df[df['isCancel'] != True]

    # Все 14д — группируем по nmId
    grouped_14 = df.groupby('nmId').agg({
        'supplierArticle': 'first',
        'subject': 'first',
        'category': 'first',
        'nmId': 'count'
    }).rename(columns={'nmId': 'orders_count_14d'}).reset_index()

    # 7д — фильтруем по дате из тех же данных, без повторного запроса
    df_7 = df[df['date'] >= date_from_7]
    grouped_7 = df_7.groupby('nmId').agg({
        'nmId': 'count'
    }).rename(columns={'nmId': 'orders_count_7d'}).reset_index()

    # Объединяем 14д и 7д в один DataFrame
    result = grouped_14.merge(grouped_7, on='nmId', how='left')
    result['orders_count_7d'] = result['orders_count_7d'].fillna(0).astype(int)

    return result


def get_stocks_report(token: str = None, period_days: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Загружает данные через Seller Analytics Stocks Report (замена legacy stocks + orders).

    Один POST-запрос возвращает остатки и заказы по всем товарам.
    Формат возврата совместим с get_stocks() и get_orders_multi().

    Args:
        token: токен WB API
        period_days: период для данных по заказам (по умолчанию 14)

    Returns:
        (stocks_df, orders_df) — два DataFrame в том же формате,
        что возвращают get_stocks() и get_orders_multi()

    Raises:
        WBApiError: при ошибках API (включая 402 — платная подписка)
        WBTokenError: при невалидном токене
    """
    if token is None:
        token = get_token()

    date_to = datetime.now()
    date_from = date_to - timedelta(days=period_days)

    all_items = []
    offset = 0
    page_limit = 1000

    while True:
        body = {
            "currentPeriod": {
                "start": date_from.strftime("%Y-%m-%d"),
                "end": date_to.strftime("%Y-%m-%d"),
            },
            "stockType": "wb",
            "skipDeletedNm": True,
            "orderBy": {"field": "ordersCount", "mode": "desc"},
            "availabilityFilters": [],
            "offset": offset,
            "limit": page_limit,
        }

        logger.info(f"Stocks Report: offset={offset}, limit={page_limit}")
        data = post_with_retry(API_STOCKS_REPORT, token, body)

        items = []
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            items = data["data"].get("items", [])
        elif isinstance(data, dict) and isinstance(data.get("data"), list):
            items = data["data"]

        all_items.extend(items)
        logger.info(f"Stocks Report: получено {len(items)} товаров (всего {len(all_items)})")

        if len(items) < page_limit:
            break

        offset += page_limit
        time.sleep(21)  # rate limit: 3 req/min

    if not all_items:
        logger.warning("Stocks Report вернул 0 товаров")
        return pd.DataFrame(), pd.DataFrame()

    # Маппинг в формат, совместимый с get_stocks() и get_orders_multi()
    stocks_rows = []
    orders_rows = []

    for item in all_items:
        nm_id = item.get("nmID")
        if not nm_id:
            continue

        metrics = item.get("metrics", {})

        stocks_rows.append({
            "nmId": nm_id,
            "stock_qty": metrics.get("stockCount", 0),
            "in_way_from_client": metrics.get("fromClientCount", 0),
            "stock_qty_clean": max(
                metrics.get("stockCount", 0) - metrics.get("fromClientCount", 0), 0
            ),
            "supplierArticle": item.get("vendorCode", ""),
            "subject": item.get("subjectName", ""),
            "category": "",
        })

        orders_rows.append({
            "nmId": nm_id,
            "supplierArticle": item.get("vendorCode", ""),
            "subject": item.get("subjectName", ""),
            "category": "",
            "orders_count_14d": metrics.get("ordersCount", 0),
            "orders_count_7d": 0,  # Stocks Report не разделяет 7д/14д
            "avg_per_day": metrics.get("avgOrders", 0),  # готовый avg от WB
        })

    stocks_df = pd.DataFrame(stocks_rows)
    orders_df = pd.DataFrame(orders_rows)

    logger.info(f"Stocks Report: {len(stocks_df)} товаров загружено")
    return stocks_df, orders_df
