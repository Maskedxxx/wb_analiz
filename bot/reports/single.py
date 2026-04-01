"""
Генерация Excel-отчёта по одному магазину (3 листа: на исходе + нет на складе + все товары).
"""

import re
import logging

import pandas as pd
from openpyxl.comments import Comment

from bot.config import THRESHOLD_A, THRESHOLD_B, THRESHOLD_C
from bot.services.calculations import merge_wh_by_name
from bot.reports.excel_styles import (
    HYPERLINK_FONT, LEFT,
    WB_PRODUCT_URL,
    apply_header_style,
    apply_data_style,
    apply_hyperlinks,
    apply_group_colors,
    apply_legend_style,
    add_stock_comment,
    make_report_path,
)

logger = logging.getLogger(__name__)


def _build_wh_index(warehouse_rows: list[dict], product_rows: list[dict]) -> dict:
    """
    Строит индекс складов по nm_id.

    Returns:
        {nm_id: [{warehouse_name, quantity, in_way_from_client}]}
    """
    index = {}
    for wr in warehouse_rows:
        nm_id = wr['nm_id']
        index.setdefault(nm_id, []).append({
            'warehouse_name': wr['warehouse_name'],
            'quantity': wr['quantity'],
            'in_way_from_client': wr.get('in_way_from_client', 0),
        })
    return index


def _apply_stock_comments(ws, df: pd.DataFrame, stock_col: int, wh_index: dict):
    """
    Добавляет Comment с детализацией по складам к ячейкам остатка.
    Значение ячейки (stock_qty_clean) уже записано как число через DataFrame export.
    """
    for i, (_, row) in enumerate(df.iterrows()):
        row_num = i + 2  # строка 1 — шапка
        nm_id = int(row['nm_id'])

        # Комментарий с детализацией по складам
        cell = ws.cell(row=row_num, column=stock_col)
        wh_list = wh_index.get(nm_id, [])
        if wh_list:
            wh_list = merge_wh_by_name(wh_list)
            add_stock_comment(cell, wh_list)


def _apply_price_comments(ws, df: pd.DataFrame, price_col: int):
    """
    Добавляет комментарии с рекомендацией повышения цены к ячейкам цены.
    """
    for i, (_, row) in enumerate(df.iterrows()):
        row_num = i + 2
        pct = row.get('price_increase_pct', 0)
        if pct and pct > 0:
            cell = ws.cell(row=row_num, column=price_col)
            comment = Comment(f"Рекомендация: повысить на {pct}%", "WB Analiz")
            comment.width = 200
            comment.height = 50
            cell.comment = comment


def _format_days_remaining(ws, df: pd.DataFrame, days_col: int):
    """Заменяет пустые ячейки 'Дней осталось' на '—' для товаров без продаж."""
    for i, (_, row) in enumerate(df.iterrows()):
        if row.get('avg_per_day', 0) == 0:
            cell = ws.cell(row=i + 2, column=days_col)
            cell.value = "—"
            cell.number_format = "@"


def _apply_product_links(ws, article_col: int, nm_id_col: int):
    """
    Добавляет кликабельные ссылки на карточку товара в ячейки артикула.
    """
    for row in ws.iter_rows(min_row=2):
        article_cell = row[article_col - 1]
        nm_id_cell = row[nm_id_col - 1]
        nm_id = nm_id_cell.value
        if nm_id is not None and article_cell.value is not None:
            article_cell.hyperlink = WB_PRODUCT_URL.format(nm_id)
            article_cell.font = HYPERLINK_FONT
            article_cell.alignment = LEFT


def generate_report_from_data(
    product_rows: list[dict],
    store_name: str = None,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
    threshold_c: float = THRESHOLD_C,
    warehouse_rows: list[dict] = None,
) -> str:
    """
    Генерирует Excel-отчёт из готовых данных (без обращения к API).

    Args:
        product_rows: список словарей с данными товаров (из БД или fetch_store_data)
        store_name: имя магазина для имени файла
        days_threshold: порог дней остатка (для аннотаций)
        threshold_a: порог группы A (для аннотаций)
        threshold_b: порог группы B (для аннотаций)
        warehouse_rows: данные по складам (опционально, для детализации остатков)

    Returns:
        Путь к сгенерированному файлу
    """
    logger.info("=== Генерация Excel-отчёта ===")

    df = pd.DataFrame(product_rows)

    if df.empty:
        logger.warning("Нет данных для отчёта")
        df = pd.DataFrame(columns=[
            'nm_id', 'supplier_article', 'subject', 'category',
            'product_group', 'stock_qty', 'in_way_from_client', 'stock_qty_clean',
            'orders_7d', 'orders_14d', 'orders_30d',
            'avg_per_day', 'days_remaining', 'price_increase_pct', 'price',
        ])

    # Индекс складов для комментариев
    wh_index = _build_wh_index(warehouse_rows, product_rows) if warehouse_rows else {}

    # Лист 1: Товары на исходе (есть остаток И нужно повышение цены)
    report = df[(df['stock_qty'] > 0) & (df['price_increase_pct'] > 0)].copy()
    report = report.sort_values('days_remaining')
    logger.info(f"Товаров на исходе: {len(report)}")

    # Лист 2: Товары с нулевым остатком
    out_of_stock = df[df['stock_qty'] == 0].copy()
    out_of_stock = out_of_stock.sort_values(['product_group', 'avg_per_day'], ascending=[True, False])
    logger.info(f"Товаров с нулевым остатком: {len(out_of_stock)}")

    # Лист 3: Все товары
    all_products = df.copy()
    all_products = all_products.sort_values('avg_per_day', ascending=False)
    logger.info(f"Всего товаров: {len(all_products)}")

    # Путь к файлу
    safe_name = re.sub(r'[^\w\s-]', '', store_name).strip()[:50] if store_name else ""
    name_part = f"_{safe_name}" if safe_name else ""
    output_path = make_report_path(f'price_report{name_part}')

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # ── Лист 1: На исходе ────────────────────────────────────────────
        report_export = report[[
            'supplier_article', 'nm_id', 'product_group',
            'stock_qty_clean', 'in_way_from_client',
            'avg_per_day', 'days_remaining', 'price'
        ]].copy()
        report_export.columns = [
            'Артикул', 'ID (WB)', 'Группа',
            'Остаток', '_iwfc',
            'Продаж/день', 'Дней осталось', 'Цена ₽'
        ]
        report_export.to_excel(writer, sheet_name='На исходе', index=False)

        # ── Лист 2: Нет на складе ───────────────────────────────────────
        out_of_stock_export = out_of_stock[[
            'supplier_article', 'nm_id', 'product_group', 'avg_per_day', 'price'
        ]].copy()
        out_of_stock_export.columns = ['Артикул', 'ID (WB)', 'Группа', 'Продаж/день', 'Цена ₽']
        out_of_stock_export.to_excel(writer, sheet_name='Нет на складе', index=False)

        # ── Лист 3: Все товары ───────────────────────────────────────────
        all_export = all_products[[
            'supplier_article', 'nm_id', 'product_group',
            'stock_qty_clean', 'in_way_from_client',
            'avg_per_day', 'days_remaining', 'price'
        ]].copy()
        all_export.columns = [
            'Артикул', 'ID (WB)', 'Группа',
            'Остаток', '_iwfc',
            'Продаж/день', 'Дней осталось', 'Цена ₽'
        ]
        all_export.to_excel(writer, sheet_name='Все товары', index=False)

        # Итоги внизу листа 2
        ws2 = writer.sheets['Нет на складе']
        last_row = len(out_of_stock_export) + 3
        ws2.cell(row=last_row, column=1, value=f'Товаров с нулевым остатком: {len(out_of_stock)}')
        ws2.cell(row=last_row + 1, column=1, value=f'Упущенные продажи в день: {out_of_stock["avg_per_day"].sum():.2f} шт')

        # ── Форматирование ───────────────────────────────────────────────
        logger.info("Форматирование Excel...")

        ws1 = writer.sheets['На исходе']
        ws3 = writer.sheets['Все товары']

        # --- Лист 1: На исходе ---
        # Колонки: 1=Артикул, 2=ID(WB), 3=Группа, 4=Остаток, 5=_iwfc, 6=Продаж/день, 7=Дней осталось, 8=Цена
        apply_header_style(ws1, {1: 24, 2: 15, 3: 11, 4: 15, 5: 0, 6: 15, 7: 17, 8: 13})
        apply_data_style(ws1, float_cols=[6, 7, 8], int_cols=[4])
        apply_hyperlinks(ws1, link_col=2)
        apply_group_colors(ws1, group_col=3)

        # Скрыть вспомогательную колонку _iwfc (col 5)
        ws1.column_dimensions['E'].hidden = True

        # Прочерк для товаров без продаж (col 7)
        _format_days_remaining(ws1, report, days_col=7)

        # Комментарии к остаткам (col 4) и ценам (col 8)
        _apply_stock_comments(ws1, report, stock_col=4, wh_index=wh_index)
        _apply_price_comments(ws1, report, price_col=8)

        # --- Лист 2: Нет на складе ---
        apply_header_style(ws2, {1: 24, 2: 15, 3: 11, 4: 15, 5: 13})
        apply_data_style(ws2, float_cols=[4, 5], int_cols=[])
        apply_hyperlinks(ws2, link_col=2)
        apply_group_colors(ws2, group_col=3)

        # --- Лист 3: Все товары ---
        # Колонки: 1=Артикул, 2=ID(WB), 3=Группа, 4=Остаток, 5=_iwfc, 6=Продаж/день, 7=Дней осталось, 8=Цена
        apply_header_style(ws3, {1: 24, 2: 15, 3: 11, 4: 15, 5: 0, 6: 15, 7: 17, 8: 13})
        apply_data_style(ws3, float_cols=[6, 7, 8], int_cols=[4])
        apply_hyperlinks(ws3, link_col=2)
        apply_group_colors(ws3, group_col=3)

        # Скрыть вспомогательную колонку _iwfc (col 5)
        ws3.column_dimensions['E'].hidden = True

        # Прочерк для товаров без продаж (col 7)
        _format_days_remaining(ws3, all_products, days_col=7)

        # Комментарии к остаткам (col 4)
        _apply_stock_comments(ws3, all_products, stock_col=4, wh_index=wh_index)

        # Ссылки на карточку товара по артикулу (col 1 → nmId из col 2)
        _apply_product_links(ws3, article_col=1, nm_id_col=2)

        # ── Аннотации под таблицами ──────────────────────────────────────
        ws1_last = len(report_export) + 4
        ws1.cell(row=ws1_last, column=1, value='— Группы товаров (продаж/день) —')
        ws1.cell(row=ws1_last + 1, column=1, value=f'A: ходовые (≥{threshold_a})')
        ws1.cell(row=ws1_last + 2, column=1, value=f'B: средние (≥{threshold_b})')
        ws1.cell(row=ws1_last + 3, column=1, value=f'C: редкие (≥{threshold_c})')
        ws1.cell(row=ws1_last + 4, column=1, value=f'D: почти не продаются (<{threshold_c})')
        ws1.cell(row=ws1_last + 5, column=1, value=f'Порог повышения цены: ≤{days_threshold} дней остатка')
        apply_legend_style(ws1, ws1_last, has_threshold_row=True)

        ws2_last = last_row + 4
        ws2.cell(row=ws2_last, column=1, value='— Группы товаров (продаж/день) —')
        ws2.cell(row=ws2_last + 1, column=1, value=f'A: ходовые (≥{threshold_a})')
        ws2.cell(row=ws2_last + 2, column=1, value=f'B: средние (≥{threshold_b})')
        ws2.cell(row=ws2_last + 3, column=1, value=f'C: редкие (≥{threshold_c})')
        ws2.cell(row=ws2_last + 4, column=1, value=f'D: почти не продаются (<{threshold_c})')
        apply_legend_style(ws2, ws2_last, has_threshold_row=False)

    logger.info(f"✓ Отчёт сохранён: {output_path}")
    logger.info("=== Генерация завершена ===")

    return output_path
