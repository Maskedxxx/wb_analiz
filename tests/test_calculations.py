"""
Тесты бизнес-логики: группировка, расчёты, merge.
"""

import pandas as pd
import pytest

from bot.services.calculations import (
    assign_group,
    calc_days_remaining,
    get_price_increase,
    merge_orders_stocks,
    merge_wh_by_name,
    aggregate_by_article,
)


# ── assign_group ─────────────────────────────────────────────────────────────

class TestAssignGroup:
    def test_group_a(self):
        assert assign_group(5.0) == 'A'

    def test_group_a_threshold(self):
        assert assign_group(4.0) == 'A'

    def test_group_b(self):
        assert assign_group(1.0) == 'B'

    def test_group_b_threshold(self):
        assert assign_group(0.5) == 'B'

    def test_group_c(self):
        assert assign_group(0.3) == 'C'

    def test_group_d_zero(self):
        assert assign_group(0) == 'D'

    def test_custom_thresholds(self):
        assert assign_group(2.0, threshold_a=10, threshold_b=5) == 'C'
        assert assign_group(7.0, threshold_a=10, threshold_b=5) == 'B'
        assert assign_group(15.0, threshold_a=10, threshold_b=5) == 'A'


# ── calc_days_remaining ──────────────────────────────────────────────────────

class TestCalcDaysRemaining:
    def test_normal(self):
        row = pd.Series({'stock_qty': 100, 'avg_per_day': 10})
        assert calc_days_remaining(row) == 10.0

    def test_zero_sales(self):
        row = pd.Series({'stock_qty': 100, 'avg_per_day': 0})
        assert calc_days_remaining(row) is None

    def test_zero_stock(self):
        row = pd.Series({'stock_qty': 0, 'avg_per_day': 5})
        assert calc_days_remaining(row) == 0.0


# ── get_price_increase ───────────────────────────────────────────────────────

class TestGetPriceIncrease:
    def test_no_increase_above_threshold(self):
        assert get_price_increase(10.0) == 0

    def test_no_increase_none(self):
        assert get_price_increase(None) == 0

    def test_max_increase(self):
        assert get_price_increase(0.5) == 50

    def test_scale_steps(self):
        assert get_price_increase(6.5) == 5
        assert get_price_increase(5.5) == 10
        assert get_price_increase(4.5) == 15
        assert get_price_increase(3.5) == 25
        assert get_price_increase(2.5) == 30
        assert get_price_increase(1.5) == 40


# ── merge_orders_stocks (OUTER JOIN) ─────────────────────────────────────────

class TestMergeOrdersStocks:
    def test_outer_join_keeps_all_products(self, stocks_df, orders_df):
        """OUTER JOIN: товары из stocks + orders = 4 уникальных nm_id."""
        df = merge_orders_stocks(orders_df, stocks_df)
        assert len(df) == 4
        assert set(df['nmId']) == {100, 200, 300, 400}

    def test_product_without_orders_has_zero_counts(self, stocks_df, orders_df):
        """nmId 300 — есть на складе, нет заказов → orders_count = 0."""
        df = merge_orders_stocks(orders_df, stocks_df)
        row_300 = df[df['nmId'] == 300].iloc[0]
        assert row_300['orders_count_7d'] == 0
        assert row_300['orders_count_14d'] == 0
        assert row_300['stock_qty'] == 5

    def test_product_without_stock_has_zero_qty(self, stocks_df, orders_df):
        """nmId 400 — есть заказы, нет на складе → stock_qty = 0."""
        df = merge_orders_stocks(orders_df, stocks_df)
        row_400 = df[df['nmId'] == 400].iloc[0]
        assert row_400['stock_qty'] == 0
        assert row_400['orders_count_14d'] == 2

    def test_metadata_from_stocks_preferred(self, stocks_df, orders_df):
        """Метаданные берутся из stocks, fallback на orders."""
        df = merge_orders_stocks(orders_df, stocks_df)
        row_100 = df[df['nmId'] == 100].iloc[0]
        assert row_100['supplierArticle'] == 'ART-1'
        assert row_100['subject'] == 'Футболка'

    def test_metadata_fallback_to_orders(self, stocks_df, orders_df):
        """nmId 400 — метаданные только из orders."""
        df = merge_orders_stocks(orders_df, stocks_df)
        row_400 = df[df['nmId'] == 400].iloc[0]
        assert row_400['supplierArticle'] == 'ART-4'
        assert row_400['subject'] == 'Носки'

    def test_sorted_by_stock_desc(self, stocks_df, orders_df):
        """Результат отсортирован по stock_qty убыванию."""
        df = merge_orders_stocks(orders_df, stocks_df)
        stock_values = df['stock_qty'].tolist()
        assert stock_values == sorted(stock_values, reverse=True)

    def test_empty_orders(self, stocks_df):
        """Если заказов нет — все товары из stocks с нулевыми orders."""
        empty_orders = pd.DataFrame(columns=['nmId', 'supplierArticle', 'subject', 'category',
                                              'orders_count_7d', 'orders_count_14d'])
        df = merge_orders_stocks(empty_orders, stocks_df)
        assert len(df) == 3
        assert (df['orders_count_14d'] == 0).all()

    def test_empty_stocks(self, orders_df):
        """Если остатков нет — все товары из orders с нулевыми stock_qty."""
        empty_stocks = pd.DataFrame(columns=['nmId', 'stock_qty', 'in_way_from_client',
                                              'stock_qty_clean', 'supplierArticle', 'subject', 'category'])
        df = merge_orders_stocks(orders_df, empty_stocks)
        assert len(df) == 3
        assert (df['stock_qty'] == 0).all()


# ── merge_wh_by_name ────────────────────────────────────────────────────────

class TestMergeWhByName:
    def test_merge_same_warehouse(self):
        wh_list = [
            {'warehouse_name': 'Коледино', 'quantity': 10, 'in_way_from_client': 1},
            {'warehouse_name': 'Коледино', 'quantity': 5, 'in_way_from_client': 2},
        ]
        result = merge_wh_by_name(wh_list)
        assert len(result) == 1
        assert result[0]['quantity'] == 15
        assert result[0]['in_way_from_client'] == 3

    def test_different_warehouses(self):
        wh_list = [
            {'warehouse_name': 'Коледино', 'quantity': 10, 'in_way_from_client': 0},
            {'warehouse_name': 'Казань', 'quantity': 5, 'in_way_from_client': 0},
        ]
        result = merge_wh_by_name(wh_list)
        assert len(result) == 2

    def test_empty_list(self):
        assert merge_wh_by_name([]) == []


# ── aggregate_by_article ─────────────────────────────────────────────────────

class TestAggregateByArticle:
    def test_aggregation(self, product_rows):
        result = aggregate_by_article(product_rows)
        assert len(result) == 3
        assert 'ART-1' in result
        assert result['ART-1']['stock_qty'] == 48

    def test_duplicate_articles_sum_stock(self):
        rows = [
            {'nm_id': 1, 'supplier_article': 'ART-X', 'stock_qty': 10,
             'stock_qty_clean': 10, 'in_way_from_client': 0,
             'avg_per_day': 1.0, 'price': 100},
            {'nm_id': 2, 'supplier_article': 'ART-X', 'stock_qty': 20,
             'stock_qty_clean': 20, 'in_way_from_client': 0,
             'avg_per_day': 2.0, 'price': 150},
        ]
        result = aggregate_by_article(rows)
        assert len(result) == 1
        assert result['ART-X']['stock_qty'] == 30
        assert result['ART-X']['avg_per_day'] == 3.0

    def test_skips_empty_article(self):
        rows = [
            {'nm_id': 1, 'supplier_article': None, 'stock_qty': 10},
            {'nm_id': 2, 'supplier_article': '', 'stock_qty': 20},
        ]
        result = aggregate_by_article(rows)
        assert len(result) == 0

    def test_zero_sales_group_d(self, product_rows):
        result = aggregate_by_article(product_rows)
        assert result['ART-3']['product_group'] == 'D'
        assert result['ART-3']['days_remaining'] is None
