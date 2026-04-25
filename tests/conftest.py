"""
Общие фикстуры для тестов.
"""

import pytest
import pandas as pd


@pytest.fixture
def stocks_df():
    """Остатки: 3 товара с метаданными (включая один без заказов)."""
    return pd.DataFrame({
        'nmId': [100, 200, 300],
        'stock_qty': [50, 10, 5],
        'in_way_from_client': [2, 0, 1],
        'stock_qty_clean': [48, 10, 4],
        'supplierArticle': ['ART-1', 'ART-2', 'ART-3'],
        'subject': ['Футболка', 'Штаны', 'Кепка'],
        'category': ['Одежда', 'Одежда', 'Аксессуары'],
    })


@pytest.fixture
def orders_df():
    """Заказы за 14д: 3 товара (400 — есть заказы, но нет на складе)."""
    return pd.DataFrame({
        'nmId': [100, 200, 400],
        'supplierArticle': ['ART-1', 'ART-2', 'ART-4'],
        'subject': ['Футболка', 'Штаны', 'Носки'],
        'category': ['Одежда', 'Одежда', 'Одежда'],
        'orders_count_7d': [10, 3, 1],
        'orders_count_14d': [20, 5, 2],
    })


@pytest.fixture
def product_rows():
    """Готовые данные товаров (как из fetch_store_data)."""
    return [
        {
            'nm_id': 100, 'supplier_article': 'ART-1', 'barcode': '2000000000001',
            'subject': 'Футболка', 'category': 'Одежда',
            'product_group': 'A', 'stock_qty': 48,
            'in_way_from_client': 2, 'stock_qty_clean': 48,
            'orders_7d': 10, 'orders_14d': 20,
            'orders_30d': None, 'avg_per_day': 1.43,
            'days_remaining': 33.6, 'price_increase_pct': 10, 'price': 1500.0,
            'availability': 'deficient', 'sale_rate_days': 33.6,
            'office_missing_days': 7.0, 'lost_orders': 3.4, 'trend_pct': 15.0,
        },
        {
            'nm_id': 200, 'supplier_article': 'ART-2', 'barcode': '2000000000002',
            'subject': 'Штаны', 'category': 'Одежда',
            'product_group': 'B', 'stock_qty': 10,
            'in_way_from_client': 0, 'stock_qty_clean': 10,
            'orders_7d': 3, 'orders_14d': 5,
            'orders_30d': None, 'avg_per_day': 0.36,
            'days_remaining': 27.8, 'price_increase_pct': 5, 'price': 2500.0,
            'availability': 'nonLiquid', 'sale_rate_days': 27.8,
            'office_missing_days': 0.0, 'lost_orders': 0.0, 'trend_pct': -8.0,
        },
        {
            'nm_id': 300, 'supplier_article': 'ART-3', 'barcode': '',
            'subject': 'Кепка', 'category': 'Аксессуары',
            'product_group': 'C', 'stock_qty': 4,
            'in_way_from_client': 1, 'stock_qty_clean': 4,
            'orders_7d': 0, 'orders_14d': 0,
            'orders_30d': None, 'avg_per_day': 0,
            'days_remaining': None, 'price_increase_pct': 0, 'price': 800.0,
            'availability': '', 'sale_rate_days': 0.0,
            'office_missing_days': 0.0, 'lost_orders': 0.0, 'trend_pct': 0.0,
        },
    ]


@pytest.fixture
def warehouse_rows():
    """Данные по складам."""
    return [
        {'nm_id': 100, 'warehouse_name': 'Коледино', 'quantity': 30, 'in_way_from_client': 2, 'supplier_article': 'ART-1'},
        {'nm_id': 100, 'warehouse_name': 'Казань', 'quantity': 20, 'in_way_from_client': 0, 'supplier_article': 'ART-1'},
        {'nm_id': 200, 'warehouse_name': 'Коледино', 'quantity': 10, 'in_way_from_client': 0, 'supplier_article': 'ART-2'},
        {'nm_id': 300, 'warehouse_name': 'Коледино', 'quantity': 5, 'in_way_from_client': 1, 'supplier_article': 'ART-3'},
    ]
