"""
Тесты генерации отчётов: проверка что Excel-файлы создаются корректно.
"""

import os

import pytest
from openpyxl import load_workbook

from bot.reports.single import generate_report_from_data
from bot.reports.comparison import generate_comparison_report
from bot.reports.summary import generate_summary_report


class TestSingleReport:
    def test_generates_file(self, product_rows, warehouse_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        path = generate_report_from_data(
            product_rows, store_name='Test Store', warehouse_rows=warehouse_rows,
        )
        assert path is not None
        assert os.path.exists(path)

    def test_three_sheets(self, product_rows, warehouse_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        path = generate_report_from_data(
            product_rows, store_name='Test', warehouse_rows=warehouse_rows,
        )
        wb = load_workbook(path)
        assert set(wb.sheetnames) == {'На исходе', 'Нет на складе', 'Все товары'}

    def test_all_products_sheet_has_all_rows(self, product_rows, warehouse_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        path = generate_report_from_data(
            product_rows, store_name='Test', warehouse_rows=warehouse_rows,
        )
        wb = load_workbook(path)
        ws = wb['Все товары']
        # Строка 1 — шапка, данные начинаются со 2-й
        data_rows = [r for r in ws.iter_rows(min_row=2) if r[0].value is not None]
        assert len(data_rows) == len(product_rows)

    def test_empty_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        path = generate_report_from_data([], store_name='Empty')
        assert os.path.exists(path)


class TestComparisonReport:
    def test_generates_file(self, product_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        # Берём часть товаров для каждого магазина (ART-1, ART-2 общие)
        store1 = product_rows[:2]
        store2 = [product_rows[0], product_rows[2]]  # ART-1 и ART-3
        path = generate_comparison_report(store1, store2, 'Магазин 1', 'Магазин 2')
        assert path is not None
        assert os.path.exists(path)

    def test_returns_none_if_no_common(self, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        store1 = [{'nm_id': 1, 'supplier_article': 'UNIQUE-1', 'stock_qty': 10,
                    'stock_qty_clean': 10, 'in_way_from_client': 0,
                    'avg_per_day': 1.0, 'price': 100}]
        store2 = [{'nm_id': 2, 'supplier_article': 'UNIQUE-2', 'stock_qty': 5,
                    'stock_qty_clean': 5, 'in_way_from_client': 0,
                    'avg_per_day': 2.0, 'price': 200}]
        path = generate_comparison_report(store1, store2, 'S1', 'S2')
        assert path is None

    def test_common_articles_counted(self, product_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        path = generate_comparison_report(
            product_rows[:2], product_rows[:2], 'S1', 'S2',
        )
        wb = load_workbook(path)
        ws = wb.active
        # 2 общих артикула × 2 строки = 4 строки данных
        data_rows = [r for r in ws.iter_rows(min_row=2) if r[1].value is not None]
        assert len(data_rows) == 4


class TestSummaryReport:
    def test_generates_file(self, product_rows, warehouse_rows, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        all_stores = {
            'Магазин 1': product_rows[:2],
            'Магазин 2': [product_rows[0], product_rows[2]],
        }
        all_wh = {
            'Магазин 1': warehouse_rows[:3],
            'Магазин 2': [warehouse_rows[0], warehouse_rows[3]],
        }
        path = generate_summary_report(all_stores, all_wh)
        assert path is not None
        assert os.path.exists(path)

    def test_returns_none_if_no_common(self, tmp_path, monkeypatch):
        monkeypatch.setattr('bot.config.REPORTS_DIR', str(tmp_path))
        store1 = [{'nm_id': 1, 'supplier_article': 'UNIQUE-1', 'stock_qty': 10,
                    'stock_qty_clean': 10, 'in_way_from_client': 0,
                    'avg_per_day': 1.0, 'price': 100}]
        store2 = [{'nm_id': 2, 'supplier_article': 'UNIQUE-2', 'stock_qty': 5,
                    'stock_qty_clean': 5, 'in_way_from_client': 0,
                    'avg_per_day': 2.0, 'price': 200}]
        path = generate_summary_report(
            {'S1': store1, 'S2': store2}, {'S1': [], 'S2': []},
        )
        assert path is None
