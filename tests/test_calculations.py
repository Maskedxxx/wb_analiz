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
    calc_refill_qty,
    availability_ru,
    trend_arrow,
    calc_smart_refill_qty,
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


# ── calc_refill_qty ──────────────────────────────────────────────────────────

class TestCalcRefillQty:
    def test_zero_avg(self):
        assert calc_refill_qty(0, 30, 20) == 0

    def test_none_avg(self):
        assert calc_refill_qty(None, 30, 20) == 0

    def test_negative_avg(self):
        assert calc_refill_qty(-1.5, 30, 20) == 0

    def test_basic_no_reserve(self):
        # 1.5 * 10 * 1.0 = 15.0 → ceil = 15
        assert calc_refill_qty(1.5, 10, 0) == 15

    def test_basic_with_reserve(self):
        # 1.5 * 30 * 1.2 = 54.0 → ceil = 54
        assert calc_refill_qty(1.5, 30, 20) == 54

    def test_ceil_rounding(self):
        # 0.1 * 10 * 1.0 = 1.0 → ceil = 1
        assert calc_refill_qty(0.1, 10, 0) == 1
        # 0.11 * 10 * 1.0 = 1.1 → ceil = 2
        assert calc_refill_qty(0.11, 10, 0) == 2

    def test_high_reserve(self):
        # 2 * 60 * 1.5 = 180 → ceil = 180
        assert calc_refill_qty(2.0, 60, 50) == 180

    def test_fractional_result_ceil(self):
        # 0.7 * 30 * 1.2 = 25.2 → ceil = 26
        assert calc_refill_qty(0.7, 30, 20) == 26


# ── availability_ru ──────────────────────────────────────────────────────────

class TestAvailabilityRu:
    def test_known_values(self):
        assert availability_ru('deficient') == 'дефицит'
        assert availability_ru('balanced') == 'баланс'
        assert availability_ru('actual') == 'ликвид'
        assert availability_ru('nonActual') == 'слабый'
        assert availability_ru('nonLiquid') == 'неликвид'

    def test_empty(self):
        assert availability_ru('') == '—'
        assert availability_ru(None) == '—'

    def test_unknown(self):
        assert availability_ru('whatever') == '—'


# ── trend_arrow ──────────────────────────────────────────────────────────────

class TestTrendArrow:
    def test_stable_zero(self):
        assert trend_arrow(0) == '→ ±0%'

    def test_stable_small(self):
        assert trend_arrow(3) == '→ ±3%'
        assert trend_arrow(-2) == '→ ±2%'

    def test_up(self):
        assert trend_arrow(15) == '↑ +15%'

    def test_down(self):
        # f'{-25:+.0f}%' → '-25%'
        assert trend_arrow(-25) == '↓ -25%'

    def test_none(self):
        assert trend_arrow(None) == '—'


# ── calc_smart_refill_qty ────────────────────────────────────────────────────

class TestCalcSmartRefillQty:
    def test_zero_avg(self):
        assert calc_smart_refill_qty(0, 30, 20) == 0

    def test_negative_avg(self):
        assert calc_smart_refill_qty(-1, 30, 20) == 0

    def test_nonliquid_returns_zero(self):
        assert calc_smart_refill_qty(1.0, 30, 20, 'nonLiquid', 5, 10) == 0

    def test_default_no_metrics(self):
        # base = 1*30*1.2 = 36; f_avail=1, f_miss=1, f_trend=1 → 36
        assert calc_smart_refill_qty(1.0, 30, 20) == 36

    def test_deficient_with_high_miss(self):
        # base=1*30*1.2=36; f_avail=1.25; miss=11 → f_miss=1.05;
        # trend=40 → f_trend=1.40
        # 36*1.25*1.05*1.40 = 66.15 → ceil = 67
        assert calc_smart_refill_qty(1.0, 30, 20, 'deficient', 11, 40) == 67

    def test_trend_clamp_upper(self):
        # balanced; miss=0; trend=500 → clamp 50 → f_trend=1.50
        # base=1*30*1.0=30; 30*1.50 = 45
        assert calc_smart_refill_qty(1.0, 30, 0, 'balanced', 0, 500) == 45

    def test_trend_clamp_lower(self):
        # balanced; trend=-99 → clamp -40 → f_trend=0.60
        # base=1*30*1.0=30; 30*0.60 = 18
        assert calc_smart_refill_qty(1.0, 30, 0, 'balanced', 0, -99) == 18

    def test_nonactual_penalty(self):
        # nonActual: f_avail=0.7; base=1*30*1=30 → 21
        assert calc_smart_refill_qty(1.0, 30, 0, 'nonActual', 0, 0) == 21

    def test_strong_decline(self):
        """Падающий товар (trend=-40%) получает заметно меньше базы."""
        # base=1*30*1.2=36; balanced; miss=0; trend=-40 → f_trend=0.60
        # 36*0.60 = 21.6 → ceil = 22
        assert calc_smart_refill_qty(1.0, 30, 20, 'balanced', 0, -40) == 22

    def test_max_combo_under_2x(self):
        """Максимальная комбинация должна быть около ~2× базовой."""
        # avg=100/30; base=100; deficient*miss>10*trend+50
        # 100 * 1.25 * 1.05 * 1.50 = 196.875 → 197
        result = calc_smart_refill_qty(100 / 30, 30, 0, 'deficient', 11, 50)
        assert result <= 200, f'Expected ≤200, got {result}'
        assert result >= 190, f'Expected ≥190 (strong boost), got {result}'
