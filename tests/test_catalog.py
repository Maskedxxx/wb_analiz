"""
Тесты: Content API каталог, фикс get_prices(), восстановление товаров в пайплайне.
"""

import json
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from bot.services.wb_client import get_prices, get_catalog, get_stocks_report
from bot.services.data_service import fetch_store_data


# ── get_prices: фикс фильтрации ─────────────────────────────────────────────

class TestGetPricesFix:
    """Проверяем что товары с ценой 0 или без размеров не теряются."""

    def _mock_prices_response(self, goods):
        """Хелпер: мок ответа Prices API (одна страница)."""
        return {'data': {'listGoods': goods}}

    @patch('bot.services.wb_client.fetch_with_retry')
    def test_zero_discounted_price(self, mock_fetch):
        mock_fetch.return_value = self._mock_prices_response([
            {'nmID': 1, 'vendorCode': 'ART-1', 'sizes': [{'discountedPrice': 0}]},
            {'nmID': 2, 'vendorCode': 'ART-2', 'sizes': [{'discountedPrice': 500}]},
        ])
        prices, articles, _barcodes = get_prices(token='test')
        assert 1 in prices
        assert prices[1] == 0
        assert prices[2] == 500
        assert articles[1] == 'ART-1'

    @patch('bot.services.wb_client.fetch_with_retry')
    def test_empty_sizes(self, mock_fetch):
        mock_fetch.return_value = self._mock_prices_response([
            {'nmID': 1, 'sizes': []},
            {'nmID': 2, 'sizes': [{'discountedPrice': 100}]},
        ])
        prices, _articles, _barcodes = get_prices(token='test')
        assert 1 in prices
        assert prices[1] == 0
        assert prices[2] == 100

    @patch('bot.services.wb_client.fetch_with_retry')
    def test_none_discounted_price(self, mock_fetch):
        mock_fetch.return_value = self._mock_prices_response([
            {'nmID': 1, 'sizes': [{'discountedPrice': None}]},
        ])
        prices, _articles, _barcodes = get_prices(token='test')
        assert 1 in prices
        assert prices[1] == 0

    @patch('bot.services.wb_client.fetch_with_retry')
    def test_mixed_sizes(self, mock_fetch):
        mock_fetch.return_value = self._mock_prices_response([
            {'nmID': 1, 'sizes': [
                {'discountedPrice': 300},
                {'discountedPrice': 200},
                {'discountedPrice': 400},
            ]},
        ])
        prices, _articles, _barcodes = get_prices(token='test')
        assert prices[1] == 200


# ── get_catalog: Content API ─────────────────────────────────────────────────

class TestGetCatalog:
    """Проверяем курсорную пагинацию и маппинг полей."""

    @patch('bot.services.wb_client.time.sleep')
    @patch('bot.services.wb_client.post_with_retry')
    def test_single_page(self, mock_post, mock_sleep):
        """Одна страница каталога — все карточки возвращаются."""
        mock_post.return_value = {
            'cards': [
                {'nmID': 1, 'vendorCode': 'ART-1', 'subjectName': 'Футболка'},
                {'nmID': 2, 'vendorCode': 'ART-2', 'subjectName': 'Штаны'},
            ],
            'cursor': {'total': 2, 'updatedAt': '', 'nmID': 0},
        }
        result = get_catalog(token='test')
        assert len(result) == 2
        assert result[1]['supplierArticle'] == 'ART-1'
        assert result[1]['subject'] == 'Футболка'
        assert result[2]['supplierArticle'] == 'ART-2'

    @patch('bot.services.wb_client.time.sleep')
    @patch('bot.services.wb_client.post_with_retry')
    def test_multi_page_pagination(self, mock_post, mock_sleep):
        """Две страницы — курсор передаётся корректно."""
        page1 = {
            'cards': [{'nmID': i, 'vendorCode': f'ART-{i}', 'subjectName': f'Item {i}'}
                       for i in range(100)],
            'cursor': {'total': 100, 'updatedAt': '2026-01-01', 'nmID': 99},
        }
        page2 = {
            'cards': [{'nmID': 100, 'vendorCode': 'ART-100', 'subjectName': 'Item 100'}],
            'cursor': {'total': 1, 'updatedAt': '2026-01-02', 'nmID': 100},
        }
        mock_post.side_effect = [page1, page2]
        result = get_catalog(token='test')
        assert len(result) == 101
        assert 0 in result
        assert 100 in result
        # Проверяем что sleep вызывался между страницами
        assert mock_sleep.call_count >= 1

    @patch('bot.services.wb_client.post_with_retry')
    def test_empty_catalog(self, mock_post):
        """Пустой каталог — пустой dict."""
        mock_post.return_value = {'cards': [], 'cursor': {'total': 0}}
        result = get_catalog(token='test')
        assert result == {}

    @patch('bot.services.wb_client.post_with_retry')
    def test_card_without_nmid_skipped(self, mock_post):
        """Карточка без nmID пропускается."""
        mock_post.return_value = {
            'cards': [
                {'vendorCode': 'BROKEN'},
                {'nmID': 1, 'vendorCode': 'OK'},
            ],
            'cursor': {'total': 2},
        }
        result = get_catalog(token='test')
        assert len(result) == 1
        assert 1 in result


# ── fetch_store_data: восстановление товаров ─────────────────────────────────

class TestFetchStoreDataRecovery:
    """Товар только в каталоге (нет в stocks/orders) → попадает в результат."""

    @patch('bot.services.data_service.get_warehouse_stocks')
    @patch('bot.services.data_service.get_stocks_report')
    @patch('bot.services.data_service.get_prices')
    @patch('bot.services.data_service.get_catalog')
    def test_product_only_in_catalog_recovered(
        self, mock_catalog, mock_prices, mock_stocks_report, mock_wh
    ):
        mock_catalog.return_value = {
            100: {'supplierArticle': 'ART-1', 'subject': 'Футболка', 'category': 'Одежда', 'barcode': ''},
            500: {'supplierArticle': 'ART-5', 'subject': 'Шарф', 'category': 'Аксессуары', 'barcode': ''},
        }
        mock_prices.return_value = (
            {100: 1500, 500: 800},
            {100: 'ART-1', 500: 'ART-5'},
            {},
        )
        stocks_df = pd.DataFrame({
            'nmId': [100],
            'stock_qty': [50],
            'in_way_from_client': [0],
            'stock_qty_clean': [50],
            'supplierArticle': ['ART-1'],
            'subject': ['Футболка'],
            'category': ['Одежда'],
        })
        orders_df = pd.DataFrame({
            'nmId': [100],
            'supplierArticle': ['ART-1'],
            'subject': ['Футболка'],
            'category': ['Одежда'],
            'orders_count_7d': [10],
            'orders_count_14d': [20],
            'avg_per_day': [1.43],
            'availability': [''],
            'sale_rate_days': [0.0],
            'office_missing_days': [0.0],
            'lost_orders': [0],
            'trend_pct': [0.0],
        })
        mock_stocks_report.return_value = (stocks_df, orders_df)
        mock_wh.return_value = pd.DataFrame()

        result = fetch_store_data(token='test')
        nm_ids = {r['nm_id'] for r in result}

        assert 500 in nm_ids
        recovered = next(r for r in result if r['nm_id'] == 500)
        assert recovered['supplier_article'] == 'ART-5'
        assert recovered['subject'] == 'Шарф'
        assert recovered['stock_qty'] == 0
        assert recovered['avg_per_day'] == 0
        assert recovered['price'] == 800

    @patch('bot.services.data_service.get_warehouse_stocks')
    @patch('bot.services.data_service.get_stocks_report')
    @patch('bot.services.data_service.get_prices')
    @patch('bot.services.data_service.get_catalog')
    def test_catalog_fallback_on_error(
        self, mock_catalog, mock_prices, mock_stocks_report, mock_wh
    ):
        mock_catalog.side_effect = Exception("Content API timeout")
        mock_prices.return_value = (
            {100: 1500, 600: 900},
            {100: 'ART-1', 600: 'ART-6'},
            {},
        )
        stocks_df = pd.DataFrame({
            'nmId': [100],
            'stock_qty': [50],
            'in_way_from_client': [0],
            'stock_qty_clean': [50],
            'supplierArticle': ['ART-1'],
            'subject': ['Футболка'],
            'category': ['Одежда'],
        })
        orders_df = pd.DataFrame(
            columns=['nmId', 'supplierArticle', 'subject', 'category',
                     'orders_count_7d', 'orders_count_14d', 'avg_per_day',
                     'availability', 'sale_rate_days', 'office_missing_days',
                     'lost_orders', 'trend_pct']
        )
        mock_stocks_report.return_value = (stocks_df, orders_df)
        mock_wh.return_value = pd.DataFrame()

        result = fetch_store_data(token='test')
        nm_ids = {r['nm_id'] for r in result}

        assert 600 in nm_ids

    @patch('bot.services.data_service.get_warehouse_stocks')
    @patch('bot.services.data_service.get_stocks_report')
    @patch('bot.services.data_service.get_prices')
    @patch('bot.services.data_service.get_catalog')
    def test_metadata_enrichment_from_catalog(
        self, mock_catalog, mock_prices, mock_stocks_report, mock_wh
    ):
        mock_catalog.return_value = {
            100: {'supplierArticle': 'ART-1', 'subject': 'Футболка', 'category': 'Одежда', 'barcode': ''},
        }
        mock_prices.return_value = ({100: 1500}, {100: 'ART-1'}, {})
        stocks_df = pd.DataFrame({
            'nmId': [100],
            'stock_qty': [50],
            'in_way_from_client': [0],
            'stock_qty_clean': [50],
            'supplierArticle': [''],
            'subject': [''],
            'category': [''],
        })
        orders_df = pd.DataFrame(
            columns=['nmId', 'supplierArticle', 'subject', 'category',
                     'orders_count_7d', 'orders_count_14d', 'avg_per_day',
                     'availability', 'sale_rate_days', 'office_missing_days',
                     'lost_orders', 'trend_pct']
        )
        mock_stocks_report.return_value = (stocks_df, orders_df)
        mock_wh.return_value = pd.DataFrame()

        result = fetch_store_data(token='test')
        item = next(r for r in result if r['nm_id'] == 100)

        assert item['supplier_article'] == 'ART-1'
        assert item['subject'] == 'Футболка'
        assert item['category'] == 'Одежда'


# ── get_stocks_report: парсинг нового API ────────────────────────────────────

class TestGetStocksReport:
    """Тесты парсинга Stocks Report API."""

    MOCK_RESPONSE = {
        "data": {
            "items": [
                {
                    "nmID": 198215260,
                    "vendorCode": "7*9бел20",
                    "subjectName": "Мешочки подарочные",
                    "metrics": {
                        "ordersCount": 1230,
                        "avgOrders": 82.0,
                        "stockCount": 1518,
                        "fromClientCount": 29,
                        "saleRate": {"days": 46, "hours": 15},
                    },
                },
                {
                    "nmID": 185297285,
                    "vendorCode": "10*12бел20",
                    "subjectName": "Мешочки подарочные",
                    "metrics": {
                        "ordersCount": 757,
                        "avgOrders": 50.47,
                        "stockCount": 1387,
                        "fromClientCount": 26,
                        "saleRate": {"days": 41, "hours": 0},
                    },
                },
            ]
        }
    }

    @patch('bot.services.wb_client.post_with_retry')
    def test_returns_two_dataframes(self, mock_post):
        """Возвращает (stocks_df, orders_df) с правильными колонками."""
        mock_post.return_value = self.MOCK_RESPONSE
        stocks, orders = get_stocks_report(token='test')

        assert len(stocks) == 2
        assert len(orders) == 2
        assert 'nmId' in stocks.columns
        assert 'stock_qty' in stocks.columns
        assert 'in_way_from_client' in stocks.columns
        assert 'stock_qty_clean' in stocks.columns
        assert 'nmId' in orders.columns
        assert 'orders_count_14d' in orders.columns

    @patch('bot.services.wb_client.post_with_retry')
    def test_stock_qty_mapping(self, mock_post):
        """stockCount маппится в stock_qty, fromClientCount в in_way_from_client."""
        mock_post.return_value = self.MOCK_RESPONSE
        stocks, _ = get_stocks_report(token='test')

        row = stocks[stocks['nmId'] == 198215260].iloc[0]
        assert row['stock_qty'] == 1518
        assert row['in_way_from_client'] == 29
        assert row['stock_qty_clean'] == 1518 - 29

    @patch('bot.services.wb_client.post_with_retry')
    def test_orders_count_mapping(self, mock_post):
        """ordersCount маппится в orders_count_14d."""
        mock_post.return_value = self.MOCK_RESPONSE
        _, orders = get_stocks_report(token='test')

        row = orders[orders['nmId'] == 198215260].iloc[0]
        assert row['orders_count_14d'] == 1230

    @patch('bot.services.wb_client.post_with_retry')
    def test_avg_per_day_from_api(self, mock_post):
        """avgOrders из API маппится в avg_per_day."""
        mock_post.return_value = self.MOCK_RESPONSE
        _, orders = get_stocks_report(token='test')

        row = orders[orders['nmId'] == 198215260].iloc[0]
        assert row['avg_per_day'] == 82.0
        row2 = orders[orders['nmId'] == 185297285].iloc[0]
        assert row2['avg_per_day'] == 50.47

    @patch('bot.services.wb_client.post_with_retry')
    def test_metadata_mapping(self, mock_post):
        """vendorCode → supplierArticle, subjectName → subject."""
        mock_post.return_value = self.MOCK_RESPONSE
        stocks, _ = get_stocks_report(token='test')

        row = stocks[stocks['nmId'] == 198215260].iloc[0]
        assert row['supplierArticle'] == '7*9бел20'
        assert row['subject'] == 'Мешочки подарочные'

    @patch('bot.services.wb_client.post_with_retry')
    def test_empty_response(self, mock_post):
        """Пустой ответ — пустые DataFrame."""
        mock_post.return_value = {"data": {"items": []}}
        stocks, orders = get_stocks_report(token='test')
        assert stocks.empty
        assert orders.empty

    @patch('bot.services.wb_client.post_with_retry')
    def test_compatible_with_merge_orders_stocks(self, mock_post):
        """Результат совместим с merge_orders_stocks из calculations.py."""
        from bot.services.calculations import merge_orders_stocks
        mock_post.return_value = self.MOCK_RESPONSE
        stocks, orders = get_stocks_report(token='test')

        merged = merge_orders_stocks(orders, stocks)
        assert len(merged) == 2
        assert 'stock_qty' in merged.columns
        assert 'orders_count_14d' in merged.columns
