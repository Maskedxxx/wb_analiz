"""
Генерация Excel-отчёта по одному магазину (3 листа: на исходе + нет на складе + все товары).
"""

import re
import logging

import pandas as pd
from openpyxl.comments import Comment
from openpyxl.styles import Font, Border, Side, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from bot.config import (
    THRESHOLD_A, THRESHOLD_B, THRESHOLD_C,
    DEFAULT_REFILL_RESERVE_PCT,
    REFILL_PERIOD_DAYS, REFILL_SAFETY_BUFFER, MAX_REFILL_WAREHOUSES,
)
from bot.services.calculations import (
    merge_wh_by_name, wh_compact_str,
    calc_smart_refill_qty, availability_ru, trend_arrow,
)
from bot.reports.excel_styles import (
    HYPERLINK_FONT, LEFT, CENTER, WRAP_LEFT,
    HEADER_FONT, HEADER_FILL, HEADER_ALIGN,
    HEADER_BG, HEADER_FG, GROUP_COLORS,
    BURNING_FILL, BARCODE_FILL,
    WB_PRODUCT_URL,
    DATA_FONT,
    apply_header_style,
    apply_data_style,
    apply_hyperlinks,
    apply_group_colors,
    apply_legend_style,
    write_legend_block,
    write_article_cell,
    write_barcode_cell,
    write_lost_orders_cell,
    write_wb_data_cells,
    write_header_row,
    add_stock_comment,
    make_report_path,
    fill,
    thin_border,
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
    """Очищает ячейки 'Дней осталось' для товаров без продаж (пустая ячейка вместо числа)."""
    for i, (_, row) in enumerate(df.iterrows()):
        if row.get('avg_per_day', 0) == 0:
            cell = ws.cell(row=i + 2, column=days_col)
            cell.value = None


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


def _style_wh_column(ws, wh_col: int, num_rows: int):
    """Стилизует колонку детализации складов (font 9/gray, без переноса текста)."""
    wh_font = Font(name="Arial", size=9, color="555555")
    for row_num in range(2, num_rows + 2):
        cell = ws.cell(row=row_num, column=wh_col)
        if cell.value is not None:
            cell.font = wh_font
            cell.alignment = LEFT


def _build_refill_calc_sheet(
    writer,
    sheet_name: str,
    product_rows: list[dict],
    warehouse_rows: list[dict],
    warehouse_distribution: list[dict],
    wh_index: dict,
    n: int = REFILL_PERIOD_DAYS,
    safety: float = REFILL_SAFETY_BUFFER,
):
    """
    Лист «Поставки - расчёт».

    Layout:
        Row 1:  Баннер
        Row 2:  Транспонированные параметры — Вес %   (cols D..K, editable)
        Row 3:  Транспонированные параметры — Отсечка (cols D..K, editable)
                Rows 2-3 = collapsible row group (развёрнуты по умолчанию)
        Row 4:  Шапка товарной таблицы (auto_filter)
        Row 5+: Данные товаров

    Видимые колонки:
        A: Артикул | B: Баркод | C: Объём | D..K: 8 складов | L: Остатки

    Скрытые: M=days_cover, N..U=stock_wh_1..8

    Заголовки складов в row 4 = формулы, динамически подтягивают вес/отсечку.
    """
    wb_book = writer.book
    if sheet_name in wb_book.sheetnames:
        del wb_book[sheet_name]
    ws = wb_book.create_sheet(sheet_name)
    writer.sheets[sheet_name] = ws

    max_wh = MAX_REFILL_WAREHOUSES  # 8
    wh_configs = warehouse_distribution[:max_wh]
    num_wh = len(wh_configs)

    # ── Константы колонок ──────────────────────────────────────────────
    COL_ART = 1       # A
    COL_BAR = 2       # B
    COL_VOL = 3       # C
    COL_WH_START = 4  # D
    COL_WH_END = COL_WH_START + max_wh - 1  # K (11)
    COL_WH_DET = COL_WH_END + 1  # L (12)
    COL_DCOVER = 13   # M — days_cover (число)
    COL_SWH_START = 14  # N — stock wh 1
    COL_SWH_END = COL_SWH_START + max_wh - 1  # U (21)

    # Строки параметров
    ROW_PARAM_WEIGHT = 2
    ROW_PARAM_CUTOFF = 3
    ROW_HEADER = 4
    ROW_DATA_START = 5

    # Буквы для формул
    L_VOL = get_column_letter(COL_VOL)       # C
    L_DCOVER = get_column_letter(COL_DCOVER)  # M

    # ── Ширины ─────────────────────────────────────────────────────────
    col_widths = {COL_ART: 26, COL_BAR: 20, COL_VOL: 12, COL_WH_DET: 36}
    for i in range(max_wh):
        col_widths[COL_WH_START + i] = 16
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    # Скрыть служебные колонки (M..U)
    for c in range(COL_DCOVER, COL_SWH_END + 1):
        ws.column_dimensions[get_column_letter(c)].hidden = True

    # Collapsible column group: склады D..K — развёрнуты по умолчанию
    ws.column_dimensions.group(
        get_column_letter(COL_WH_START), get_column_letter(COL_WH_END),
        outline_level=1, hidden=False,
    )

    # Collapsible row group: параметры rows 2-3 — развёрнуты по умолчанию
    ws.row_dimensions.group(ROW_PARAM_WEIGHT, ROW_PARAM_CUTOFF,
                            outline_level=1, hidden=False)

    # ── Стили ──────────────────────────────────────────────────────────
    data_border = thin_border()
    wh_font = Font(name='Arial', size=9, color='555555')
    stock_cell_fill = PatternFill('solid', fgColor='FFF8E1')

    # Цветовой градиент для столбцов складов (8 оттенков)
    WH_COL_FILLS = [
        PatternFill('solid', fgColor='E3F2FD'),  # light blue
        PatternFill('solid', fgColor='E8F5E9'),  # light green
        PatternFill('solid', fgColor='FFF3E0'),  # light orange
        PatternFill('solid', fgColor='F3E5F5'),  # light purple
        PatternFill('solid', fgColor='E0F7FA'),  # light cyan
        PatternFill('solid', fgColor='FFF9C4'),  # light yellow
        PatternFill('solid', fgColor='FCE4EC'),  # light pink
        PatternFill('solid', fgColor='EFEBE9'),  # light brown
    ]

    param_fill = PatternFill('solid', fgColor='E8EAF6')
    param_border = Border(
        left=Side(style='thin', color='9FA8DA'),
        right=Side(style='thin', color='9FA8DA'),
        top=Side(style='thin', color='9FA8DA'),
        bottom=Side(style='thin', color='9FA8DA'),
    )
    param_font = Font(name='Arial', size=10, color='3949AB')
    param_label_font = Font(name='Arial', size=10, bold=True, color='3949AB')

    # ── Row 1: баннер ──────────────────────────────────────────────────
    banner_font = Font(name='Arial', size=11, bold=True, color='1A1A2E')
    banner_fill = PatternFill('solid', fgColor='E7EEF7')
    banner_align = Alignment(horizontal='center', vertical='center')

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=COL_WH_DET)
    c = ws.cell(row=1, column=1, value=f'\u2014 {sheet_name} \u2014')
    c.font = banner_font
    c.fill = banner_fill
    c.alignment = banner_align
    for col in range(1, COL_WH_DET + 1):
        ws.cell(row=1, column=col).fill = banner_fill
    ws.row_dimensions[1].height = 22

    # ── Rows 2-3: транспонированные параметры (горизонтально) ──────────
    # Лейблы в col A
    ws.cell(row=ROW_PARAM_WEIGHT, column=COL_ART, value='Вес %').font = param_label_font
    ws.cell(row=ROW_PARAM_CUTOFF, column=COL_ART, value='Отсечка д').font = param_label_font

    for i in range(max_wh):
        col_wh = COL_WH_START + i
        w_cell = ws.cell(row=ROW_PARAM_WEIGHT, column=col_wh)
        c_cell = ws.cell(row=ROW_PARAM_CUTOFF, column=col_wh)
        for cell in (w_cell, c_cell):
            cell.fill = param_fill
            cell.border = param_border
            cell.font = param_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        if i < num_wh:
            wc = wh_configs[i]
            w_cell.value = wc['weight']
            c_cell.value = wc['cutoff_days']

    # ── Row 4: шапка товарной таблицы ──────────────────────────────────
    static_headers = {COL_ART: 'Артикул', COL_BAR: 'Баркод', COL_VOL: f'Объём\n{n}д', COL_WH_DET: 'Остатки по складам'}
    for col_num, title in static_headers.items():
        cell = ws.cell(row=ROW_HEADER, column=col_num, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = thin_border('444444')

    # Динамические заголовки складов (формулы)
    for i in range(max_wh):
        col_wh = COL_WH_START + i
        L_wh = get_column_letter(col_wh)
        cell = ws.cell(row=ROW_HEADER, column=col_wh)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = thin_border('444444')
        if i < num_wh:
            name = wh_configs[i].get('display_name', f'Склад {i+1}')
            # ="Коледино"&CHAR(10)&D2&"%|"&D3&"д"
            cell.value = (
                f'="{name}"&CHAR(10)&{L_wh}${ROW_PARAM_WEIGHT}'
                f'&"%|"&{L_wh}${ROW_PARAM_CUTOFF}&"\u0434"'
            )
        else:
            cell.value = '\u2014'

    # Баркод шапка — заливка
    ws.cell(row=ROW_HEADER, column=COL_BAR).fill = PatternFill('solid', fgColor=HEADER_BG)

    ws.row_dimensions[ROW_HEADER].height = 38
    ws.freeze_panes = f'A{ROW_DATA_START}'

    # Auto_filter на диапазон данных (row 4..N, cols A..L)
    last_data_row = ROW_DATA_START + len(product_rows) - 1
    if last_data_row < ROW_DATA_START:
        last_data_row = ROW_DATA_START
    ws.auto_filter.ref = f'A{ROW_HEADER}:{get_column_letter(COL_WH_DET)}{last_data_row}'

    # ── Индекс складов ─────────────────────────────────────────────────
    wh_id_set = {wc['warehouse_id'] for wc in wh_configs}

    def stock_by_wh_for_nm(nm_id):
        result = {}
        for wr in warehouse_rows:
            if wr['nm_id'] == nm_id and wr.get('warehouse_id') in wh_id_set:
                wid = wr['warehouse_id']
                result[wid] = result.get(wid, 0) + wr['quantity']
        return result

    # ── Заполнение строк данных ────────────────────────────────────────
    safety_mult = 1 + safety
    sorted_rows = sorted(product_rows, key=lambda r: r.get('avg_per_day', 0) or 0, reverse=True)

    for i, r in enumerate(sorted_rows):
        row_num = ROW_DATA_START + i
        avg = float(r.get('avg_per_day') or 0)
        nm_id = r.get('nm_id')
        barcode = r.get('barcode', '') or ''
        article = r.get('supplier_article', '') or ''

        # A: Артикул (hyperlink)
        write_article_cell(ws, row_num, COL_ART, article, nm_id, data_border)

        # B: Баркод (серая заливка)
        write_barcode_cell(ws, row_num, COL_BAR, barcode, data_border, bg_fill=BARCODE_FILL)

        # Stocks per warehouse
        stock_map = stock_by_wh_for_nm(nm_id) if nm_id and warehouse_rows else {}
        useful_stock = sum(stock_map.get(wc['warehouse_id'], 0) for wc in wh_configs)

        # C: Объём (число)
        if avg > 0:
            volume = round(avg * n * safety_mult)
            days_cover = useful_stock / avg
        else:
            volume = None
            days_cover = 9999

        vol_cell = ws.cell(row=row_num, column=COL_VOL, value=volume)
        vol_cell.font = DATA_FONT
        vol_cell.alignment = CENTER
        vol_cell.number_format = '0'
        vol_cell.border = data_border

        # Hidden M: days_cover
        ws.cell(row=row_num, column=COL_DCOVER, value=round(days_cover, 2))

        # Hidden N..U: stock per warehouse
        for wi in range(max_wh):
            s_cell = ws.cell(row=row_num, column=COL_SWH_START + wi)
            if wi < num_wh:
                wid = wh_configs[wi]['warehouse_id']
                s_cell.value = stock_map.get(wid, 0)
            else:
                s_cell.value = 0
            s_cell.fill = stock_cell_fill

        # D..K: формулы распределения по складам (с градиентной заливкой)
        for wi in range(max_wh):
            col_wh = COL_WH_START + wi
            L_wh = get_column_letter(col_wh)
            L_stock_wh = get_column_letter(COL_SWH_START + wi)
            cell_wh = ws.cell(row=row_num, column=col_wh)
            cell_wh.font = DATA_FONT
            cell_wh.alignment = CENTER
            cell_wh.number_format = '0'
            cell_wh.border = data_border
            cell_wh.fill = WH_COL_FILLS[wi]

            if wi >= num_wh:
                cell_wh.value = ''
                continue

            # =IF(OR(C5="",D$2=""),"",MAX(0,ROUND(C5*IF(M5<D$3,D$2*2,D$2)/100,0)-N5))
            cell_wh.value = (
                f'=IF(OR({L_VOL}{row_num}="",{L_wh}${ROW_PARAM_WEIGHT}=""),"",'
                f'MAX(0,ROUND({L_VOL}{row_num}'
                f'*IF({L_DCOVER}{row_num}<{L_wh}${ROW_PARAM_CUTOFF},'
                f'{L_wh}${ROW_PARAM_WEIGHT}*2,{L_wh}${ROW_PARAM_WEIGHT})/100,0)'
                f'-{L_stock_wh}{row_num}))'
            )

        # L: Остатки по складам (текст)
        wh_str = wh_compact_str(wh_index.get(nm_id, [])) if nm_id else '\u2014'
        wh_det_cell = ws.cell(row=row_num, column=COL_WH_DET, value=wh_str)
        wh_det_cell.font = wh_font
        wh_det_cell.alignment = WRAP_LEFT
        wh_det_cell.border = data_border

    # ── Легенда ─────────────────────────────────────────────────────────
    legend_start = ROW_DATA_START + len(sorted_rows) + 1
    write_legend_block(ws, legend_start, [
        ('— Поставки: расчёт —', 'title'),
        (f'Объём = avg_day × {n}д × (1 + буфер%). Буфер задаётся в настройках бота.', 'item'),
        ('Скрытые колонки M..U: дней покрытия (M) и остатки по каждому складу (N..U) — для формул.', 'note'),
        ('Параметры складов (строки 2-3): Вес % и Отсечка — редактируются прямо в таблице.', 'item'),
        ('Объём в колонке C можно вручную скорректировать — формулы складов пересчитаются автоматически.', 'item'),
        ('Формула склада: MAX(0, ROUND(Объём × Вес/100 × коэф, 0) − Остаток_склад)', 'note'),
        ('коэф = 2, если дней покрытия < Отсечка (товар заканчивается); иначе = 1.', 'note'),
    ])

    logger.info(f"Лист '{sheet_name}': {len(sorted_rows)} товаров записано")


def _build_wb_suggestion_sheet(
    writer,
    sheet_name: str,
    product_rows: list[dict],
    n: int = REFILL_PERIOD_DAYS,
    reserve_pct: float = DEFAULT_REFILL_RESERVE_PCT,
):
    """
    Лист «Поставки - предложение» — блок WB-метрик по ВСЕМ товарам.

    Компоновка:
        A: Артикул | B: Баркод | C: Объём WB | D: Оборотность |
        E: Простой поставки | F: Упущено | G: Срок продаж (WB) | H: Тренд
    """
    wb_book = writer.book
    if sheet_name in wb_book.sheetnames:
        del wb_book[sheet_name]
    ws = wb_book.create_sheet(sheet_name)
    writer.sheets[sheet_name] = ws

    # ── Шапка ──────────────────────────────────────────────────────────
    headers = [
        'Артикул', 'Баркод', 'Объём WB', 'Оборотность',
        'Простой поставки', 'Упущено заказов', 'Срок продаж (WB)', 'Тренд',
    ]
    col_widths = {1: 26, 2: 20, 3: 12, 4: 14, 5: 16, 6: 16, 7: 22, 8: 12}

    write_header_row(ws, 1, headers)
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = 'A2'

    # Auto_filter
    last_row = 1 + len(product_rows)
    if last_row < 2:
        last_row = 2
    ws.auto_filter.ref = f'A1:H{last_row}'

    # ── Данные ──────────────────────────────────────────────────────────
    data_border = thin_border()

    sorted_rows = sorted(product_rows, key=lambda r: r.get('avg_per_day', 0) or 0, reverse=True)

    for i, r in enumerate(sorted_rows):
        row_num = i + 2
        avg = float(r.get('avg_per_day') or 0)
        nm_id = r.get('nm_id')
        barcode = r.get('barcode', '') or ''
        article = r.get('supplier_article', '') or ''
        avail = (r.get('availability') or '')
        miss = float(r.get('office_missing_days') or 0)
        lost = float(r.get('lost_orders') or 0)
        trend = float(r.get('trend_pct') or 0)
        sale_rate = float(r.get('sale_rate_days') or 0)

        smart_qty = calc_smart_refill_qty(avg, n, reserve_pct, avail, miss, trend)

        # A: Артикул
        write_article_cell(ws, row_num, 1, article, nm_id, data_border)

        # B: Баркод
        write_barcode_cell(ws, row_num, 2, barcode, data_border)

        # C-H: WB метрики
        write_wb_data_cells(
            ws, row_num, 3,
            smart_qty if avg > 0 else None,
            availability_ru(avail), miss, lost, sale_rate,
            trend_arrow(trend), trend,
            border_vol=data_border, border_data=data_border,
            lost_zero_value=None,
        )

    logger.info(f"Лист '{sheet_name}': {len(sorted_rows)} товаров записано")



def generate_report_from_data(
    product_rows: list[dict],
    store_name: str = None,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
    threshold_c: float = THRESHOLD_C,
    warehouse_rows: list[dict] = None,
    refill_reserve_pct: float = DEFAULT_REFILL_RESERVE_PCT,
    refill_period_days: int = REFILL_PERIOD_DAYS,
    warehouse_distribution: list[dict] = None,
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
            'nm_id', 'supplier_article', 'barcode', 'subject', 'category',
            'product_group', 'stock_qty', 'in_way_from_client', 'stock_qty_clean',
            'orders_7d', 'orders_14d', 'orders_30d',
            'avg_per_day', 'days_remaining', 'price_increase_pct', 'price',
        ])

    # Fallback для barcode (старые данные из БД могут не содержать колонку)
    if 'barcode' not in df.columns:
        df['barcode'] = ''
    df['barcode'] = df['barcode'].fillna('')

    # Индекс складов для комментариев и детализации
    wh_index = _build_wh_index(warehouse_rows, product_rows) if warehouse_rows else {}

    # Детализация остатков по складам (компактная строка)
    df['wh_detail'] = df.apply(
        lambda r: wh_compact_str(wh_index.get(int(r['nm_id']), []))
        if (r.get('stock_qty_clean') or 0) > 0 else "—",
        axis=1,
    )

    # Все товары
    all_products = df.copy()
    all_products = all_products.sort_values('avg_per_day', ascending=False)
    logger.info(f"Всего товаров: {len(all_products)}")

    # Путь к файлу
    safe_name = re.sub(r'[^\w\s-]', '', store_name).strip()[:50] if store_name else ""
    name_part = f"_{safe_name}" if safe_name else ""
    output_path = make_report_path(f'price_report{name_part}')

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # ── Лист 1: Все товары ─────────────────────────────────────────
        all_export = all_products[[
            'supplier_article', 'barcode', 'nm_id', 'product_group',
            'stock_qty_clean', 'in_way_from_client',
            'avg_per_day', 'days_remaining', 'price', 'wh_detail'
        ]].copy()
        all_export.columns = [
            'Артикул', 'Баркод', 'ID (WB)', 'Группа',
            'Остаток\n(чистый)', '_iwfc',
            'Продаж/день', 'Дней осталось', 'Цена ₽', 'Остатки по складам'
        ]
        all_export.to_excel(writer, sheet_name='Все товары', index=False)

        # ── Лист «Поставки - расчёт» (все товары, распределение по складам) ─
        _build_refill_calc_sheet(
            writer, 'Поставки - расчёт',
            product_rows, warehouse_rows or [],
            warehouse_distribution or [], wh_index,
            n=refill_period_days,
        )

        # ── Лист «Поставки - предложение» (WB-метрики, все товары) ─────
        _build_wb_suggestion_sheet(
            writer, 'Поставки - предложение',
            product_rows,
            n=refill_period_days,
        )

        # ── Форматирование «Все товары» ────────────────────────────────
        logger.info("Форматирование Excel...")

        ws = writer.sheets['Все товары']

        # Колонки: 1=Артикул, 2=Баркод, 3=ID(WB), 4=Группа, 5=Остаток, 6=_iwfc, 7=Продаж/день, 8=Дней осталось, 9=Цена, 10=Остатки по складам
        apply_header_style(ws, {1: 24, 2: 18, 3: 15, 4: 11, 5: 15, 6: 0, 7: 15, 8: 17, 9: 13, 10: 32})
        apply_data_style(ws, float_cols=[7, 8, 9], int_cols=[5], row_height=None)
        apply_hyperlinks(ws, link_col=3)
        apply_group_colors(ws, group_col=4)

        # Скрыть вспомогательную колонку _iwfc (col 6)
        ws.column_dimensions['F'].hidden = True

        # Пустые ячейки для товаров без продаж (col 8)
        _format_days_remaining(ws, all_products, days_col=8)

        # Комментарии к остаткам (col 5) и рекомендации повышения цен (col 9)
        _apply_stock_comments(ws, all_products, stock_col=5, wh_index=wh_index)
        _apply_price_comments(ws, all_products, price_col=9)

        # Ссылки на карточку товара по артикулу (col 1 → nmId из col 3)
        _apply_product_links(ws, article_col=1, nm_id_col=3)

        # Стилизация колонки складов (col 10)
        _style_wh_column(ws, wh_col=10, num_rows=len(all_export))

        # Легенда
        legend_start = len(all_export) + 3  # +1 шапка, +1 пустая строка
        write_legend_block(ws, legend_start, [
            ('— Группы товаров —', 'title'),
            ('A — высокие продажи (быстрые)', 'item'),
            ('B — средние продажи', 'item'),
            ('C — низкие продажи (медленные)', 'item'),
            ('D — почти нет продаж (неликвид)', 'item'),
            ('Границы групп задаются в настройках бота (Параметры расчёта → Границы групп).', 'note'),
            ('', 'note'),
            ('— Колонки —', 'title'),
            ('Дней осталось — остаток / средние продажи в день. Пусто = нет продаж.', 'item'),
            ('Остатки по складам — детализация остатков. Наведите на ячейку для подробностей.', 'item'),
        ])

    logger.info(f"✓ Отчёт сохранён: {output_path}")
    logger.info("=== Генерация завершена ===")

    return output_path
