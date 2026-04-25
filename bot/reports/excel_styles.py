"""
Константы стилей и функции форматирования Excel для отчётов WB Analiz.
"""

from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

# ── Цветовые константы ────────────────────────────────────────────────────────

# Шапка таблицы
HEADER_BG = "2E4057"
HEADER_FG = "FFFFFF"

# Цвета групп (фон ячейки)
GROUP_COLORS = {
    "A": "B7E4C7",  # мятный зелёный
    "B": "FFD6A5",  # персиковый
    "C": "C8B6E2",  # лавандовый
    "D": "D6D6D6",  # серый
}

# Градиент повышения цены: {%: (фон, цвет_текста)}
PRICE_INCREASE_COLORS = {
    5:  ("FFF9C4", "333333"),
    10: ("FFE082", "333333"),
    15: ("FFB300", "333333"),
    25: ("FF8F00", "FFFFFF"),
    30: ("E65100", "FFFFFF"),
    40: ("BF360C", "FFFFFF"),
    50: ("7B1818", "FFFFFF"),
}

# Ссылка на кабинет продавца WB
WB_CABINET_URL = "https://seller.wildberries.ru/discount-and-prices?search={}"

# Ссылка на карточку товара в магазине WB
WB_PRODUCT_URL = "https://www.wildberries.ru/catalog/{}/detail.aspx"

# Цвета рекомендаций сравнения
CMP_RAISE_BG = "E8F5E9"   # светло-зелёный
CMP_LOWER_BG = "FFEBEE"   # светло-красный
CMP_PAIR_ALT_BG = "F5F5F5"  # чередование пар
SUMMARY_PAIR_ALT_BG = "F5F5F5"

# ── Общие стили данных ────────────────────────────────────────────────────────

DATA_FONT = Font(name="Arial", size=10, color="1A1A2E")
DATA_FONT_BOLD = Font(name="Arial", size=10, bold=True, color="1A1A2E")
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
WRAP_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
HYPERLINK_FONT = Font(name="Arial", size=10, color="1155CC", underline="single")
INNER_THIN = Side(style="thin", color="CCCCCC")
GROUP_THICK = Side(style="medium", color="888888")

HEADER_FONT = Font(name="Arial", size=11, bold=True, color=HEADER_FG)
HEADER_FILL = PatternFill("solid", fgColor=HEADER_BG)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

BURNING_FILL = PatternFill("solid", fgColor="FFCCCC")
BARCODE_FILL = PatternFill("solid", fgColor="F0F0F0")

TREND_FILL_UP = PatternFill("solid", fgColor="C8E6C9")
TREND_FILL_DOWN = PatternFill("solid", fgColor="FFCCBC")
TREND_FILL_NEUTRAL = PatternFill("solid", fgColor="EEEEEE")
TREND_THRESHOLD = 5

# ── Вспомогательные стили ─────────────────────────────────────────────────────

def thin_border(color="CCCCCC"):
    side = Side(style="thin", color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def fill(hex_color):
    return PatternFill(fill_type="solid", fgColor=hex_color)


def trend_fill(trend_pct: float) -> PatternFill:
    if trend_pct >= TREND_THRESHOLD:
        return TREND_FILL_UP
    elif trend_pct <= -TREND_THRESHOLD:
        return TREND_FILL_DOWN
    return TREND_FILL_NEUTRAL


def write_header_row(ws, row_num: int, headers: list, border_color: str = "444444"):
    for idx, title in enumerate(headers, start=1):
        cell = ws.cell(row=row_num, column=idx, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = thin_border(border_color)


def write_article_cell(ws, row_num: int, col: int, article: str, nm_id, border):
    c = ws.cell(row=row_num, column=col, value=article)
    c.font = DATA_FONT
    c.alignment = LEFT
    c.border = border
    if article and nm_id is not None:
        c.hyperlink = WB_PRODUCT_URL.format(nm_id)
        c.font = HYPERLINK_FONT


def write_barcode_cell(ws, row_num: int, col: int, barcode: str, border, bg_fill=None):
    c = ws.cell(row=row_num, column=col, value=barcode)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.number_format = "@"
    c.border = border
    if bg_fill:
        c.fill = bg_fill


def write_lost_orders_cell(ws, row_num: int, col: int, lost: float, border, zero_value=None):
    lost_rounded = round(lost)
    c = ws.cell(row=row_num, column=col,
                value=lost_rounded if lost_rounded > 0 else zero_value)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = border
    if lost_rounded > 0:
        c.fill = BURNING_FILL


def write_wb_data_cells(
    ws, row_num: int, start_col: int,
    smart_qty, avail_str: str, miss: float, lost: float,
    sale_rate: float, trend_str: str, trend_pct: float,
    border_vol, border_data, lost_zero_value=None,
):
    col = start_col

    c = ws.cell(row=row_num, column=col, value=smart_qty)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.number_format = "0"
    c.border = border_vol
    col += 1

    c = ws.cell(row=row_num, column=col, value=avail_str)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = border_data
    col += 1

    c = ws.cell(row=row_num, column=col, value=f"{miss:.0f} \u0434\u043d")
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = border_data
    col += 1

    write_lost_orders_cell(ws, row_num, col, lost, border_data, zero_value=lost_zero_value)
    col += 1

    sr_val = f"{int(max(0, sale_rate))} \u0434\u043d" if sale_rate > 0 else "\u2014"
    c = ws.cell(row=row_num, column=col, value=sr_val)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = border_data
    col += 1

    c = ws.cell(row=row_num, column=col, value=trend_str)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = border_data
    c.fill = trend_fill(trend_pct)


# ── Функции форматирования ────────────────────────────────────────────────────

def apply_header_style(ws, column_widths: dict, headers: list = None, row_height: int = 34, auto_filter: bool = True):
    """
    Тёмная шапка, фриз, авто-фильтр, высота строк, ширина столбцов.

    Args:
        ws: openpyxl worksheet
        column_widths: {col_num: width}
        headers: если передан — записывает заголовки в строку 1
        row_height: высота строки шапки
    """
    if headers:
        for col_idx, header in enumerate(headers, 1):
            ws.cell(row=1, column=col_idx, value=header)

    ws.row_dimensions[1].height = row_height
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = thin_border("444444")

    ws.freeze_panes = "A2"
    if auto_filter:
        ws.auto_filter.ref = ws.dimensions

    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width


def apply_data_style(ws, float_cols: list, int_cols: list, row_height: int = 16):
    """Шрифт, выравнивание, высота строк, числовые форматы для строк с данными."""
    data_font = Font(name="Arial", size=10, color="1A1A2E")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    border = thin_border()

    for row in ws.iter_rows(min_row=2):
        # пропускаем строки аннотаций (нет значения во 2-м столбце)
        if row[0].value is None:
            continue
        if row_height is not None:
            ws.row_dimensions[row[0].row].height = row_height
        for cell in row:
            cell.font = data_font
            cell.border = border
            cell.alignment = left if cell.column == 1 else center
            if cell.column in float_cols:
                cell.number_format = "0.00"
            elif cell.column in int_cols:
                cell.number_format = "0"


def apply_group_colors(ws, group_col: int, start_row: int = 2):
    """Окрашивает только ячейку группы товара."""
    for row in ws.iter_rows(min_row=start_row):
        cell = row[group_col - 1]
        group = cell.value
        if group in GROUP_COLORS:
            cell.fill = fill(GROUP_COLORS[group])
            cell.font = Font(name="Arial", size=10, bold=True, color="1A1A2E")


def apply_price_increase_colors(ws, pct_col: int):
    """Градиент фона + контрастный текст для ячейки % повышения."""
    for row in ws.iter_rows(min_row=2):
        cell = row[pct_col - 1]
        pct = cell.value
        if pct in PRICE_INCREASE_COLORS:
            bg, fg = PRICE_INCREASE_COLORS[pct]
            cell.fill = fill(bg)
            cell.font = Font(name="Arial", size=10, bold=True, color=fg)


def apply_legend_style(ws, start_row: int, has_threshold_row: bool = False):
    """Ненавязчивый стиль для аннотаций под таблицей."""
    title_font = Font(name="Arial", size=9, bold=True, color="888888")
    row_font = Font(name="Arial", size=9, italic=True, color="999999")
    note_font = Font(name="Arial", size=9, color="999999")
    summary_font = Font(name="Arial", size=9, bold=True, color="555555")

    # start_row: строка «— Группы товаров —»
    ws.cell(row=start_row, column=1).font = title_font
    ws.cell(row=start_row + 1, column=1).font = row_font
    ws.cell(row=start_row + 2, column=1).font = row_font
    ws.cell(row=start_row + 3, column=1).font = row_font
    ws.cell(row=start_row + 4, column=1).font = row_font
    if has_threshold_row:
        ws.cell(row=start_row + 5, column=1).font = note_font

    # Итоговые строки листа 2 (на 4 строки выше start_row: пустая + 2 итога + пустая)
    summary_row = start_row - 4
    if summary_row >= 1:
        ws.cell(row=summary_row, column=1).font = summary_font
        ws.cell(row=summary_row + 1, column=1).font = summary_font


def apply_hyperlinks(ws, link_col: int, start_row: int = 2):
    """Превращает nmId в кликабельные ссылки на кабинет WB."""
    hyperlink_font = Font(name="Arial", size=10, color="1155CC", underline="single")
    center = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=start_row):
        cell = row[link_col - 1]
        nm_id = cell.value
        if nm_id is not None:
            url = WB_CABINET_URL.format(nm_id)
            cell.hyperlink = url
            cell.value = nm_id
            cell.font = hyperlink_font
            cell.alignment = center


def write_legend_block(ws, start_row: int, lines: list[tuple[str, str]]):
    """
    Записывает блок легенды в произвольном формате.

    Args:
        lines: [(текст, тип), ...] где тип = 'title' | 'item' | 'note'
    """
    fonts = {
        'title': Font(name="Arial", size=9, bold=True, color="888888"),
        'item': Font(name="Arial", size=9, italic=True, color="999999"),
        'note': Font(name="Arial", size=9, color="999999"),
        'summary': Font(name="Arial", size=9, bold=True, color="555555"),
    }
    for i, (text, style) in enumerate(lines):
        cell = ws.cell(row=start_row + i, column=1, value=text)
        cell.font = fonts.get(style, fonts['item'])


def make_group_border(inner_thin_side, thick_side, is_top, is_bottom, col_idx, num_cols):
    """
    Универсальная рамка ячейки внутри группы (пара или N строк).

    Толстая граница сверху/снизу группы и по бокам таблицы, тонкая внутри.
    """
    top = thick_side if is_top else inner_thin_side
    bottom = thick_side if is_bottom else inner_thin_side
    left = thick_side if col_idx == 1 else inner_thin_side
    right = thick_side if col_idx == num_cols else inner_thin_side
    return Border(left=left, right=right, top=top, bottom=bottom)


def group_border_fn(is_top: bool, is_bottom: bool, col_idx: int, num_cols: int) -> Border:
    """Shortcut для make_group_border с дефолтными INNER_THIN/GROUP_THICK."""
    return make_group_border(INNER_THIN, GROUP_THICK, is_top, is_bottom, col_idx, num_cols)


def write_merged_article(ws, article: str, start_row: int, end_row: int, num_cols: int):
    """Записывает merged-ячейку артикула (колонка A) с рамкой группы."""
    if end_row > start_row:
        ws.merge_cells(start_row=start_row, start_column=1, end_row=end_row, end_column=1)
    c = ws.cell(row=start_row, column=1, value=article)
    c.font = DATA_FONT_BOLD
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    c.border = group_border_fn(True, True, 1, num_cols)
    if end_row > start_row:
        ws.cell(row=end_row, column=1).border = group_border_fn(False, True, 1, num_cols)


def apply_row_background(ws, row_num: int, bg_color: str, num_cols: int, start_col: int = 2):
    """Применяет фон чередования к строке, не перезаписывая уже окрашенные ячейки."""
    for col in range(start_col, num_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        if cell.fill == PatternFill():
            cell.fill = fill(bg_color)


def make_report_path(prefix: str) -> str:
    """Создаёт путь для отчёта с таймстампом. Гарантирует существование директории."""
    import os
    from datetime import datetime
    from bot.config import REPORTS_DIR, MSK_TZ
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now(MSK_TZ).strftime('%Y%m%d_%H%M')
    return os.path.join(REPORTS_DIR, f'{prefix}_{timestamp}.xlsx')


def write_store_row(
    ws, row_num: int, store_data: dict, store_name: str,
    is_top: bool, is_bottom: bool, num_cols: int,
    row_height: int | None = 18,
):
    """
    Записывает общие колонки строки данных магазина (B-H).

    Колонки: B=Магазин, C=ID(WB) с гиперссылкой, D=Остаток (int),
    E=Дней осталось, F=Продаж/день, G=Группа, H=Цена.

    Returns:
        Callable border_fn(col_idx) для использования в специфичных колонках.
    """
    def _border(col_idx):
        return group_border_fn(is_top, is_bottom, col_idx, num_cols)

    if row_height is not None:
        ws.row_dimensions[row_num].height = row_height

    # B: Магазин
    c = ws.cell(row=row_num, column=2, value=store_name)
    c.font = DATA_FONT
    c.alignment = LEFT
    c.border = _border(2)

    # C: ID (WB) — гиперссылка
    nm_id = store_data.get('nm_id')
    c = ws.cell(row=row_num, column=3, value=nm_id)
    if nm_id:
        c.hyperlink = WB_CABINET_URL.format(nm_id)
        c.font = HYPERLINK_FONT
    else:
        c.font = DATA_FONT
    c.alignment = CENTER
    c.border = _border(3)

    # D: Остаток
    c = ws.cell(row=row_num, column=4, value=store_data.get('stock_qty', 0))
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = _border(4)
    c.number_format = "0"

    # E: Дней осталось
    avg = store_data.get('avg_per_day', 0)
    dr = store_data.get('days_remaining')
    if avg == 0:
        c = ws.cell(row=row_num, column=5, value=None)
    else:
        c = ws.cell(row=row_num, column=5, value=dr)
        if dr is not None:
            c.number_format = "0.0"
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = _border(5)

    # F: Продаж/день
    c = ws.cell(row=row_num, column=6, value=store_data.get('avg_per_day', 0))
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = _border(6)
    c.number_format = "0.00"

    # G: Группа
    group = store_data.get('product_group', '')
    c = ws.cell(row=row_num, column=7, value=group)
    c.font = DATA_FONT_BOLD
    c.alignment = CENTER
    c.border = _border(7)
    if group in GROUP_COLORS:
        c.fill = fill(GROUP_COLORS[group])

    # H: Цена
    price = store_data.get('price')
    c = ws.cell(row=row_num, column=8, value=price)
    c.font = DATA_FONT
    c.alignment = CENTER
    c.border = _border(8)
    if price is not None:
        c.number_format = "0.00"

    return _border


def add_days_dropdown(ws, cell, days_options: list[int]):
    """
    Добавляет per-cell DataValidation(type='list') с числовыми сроками.

    Args:
        ws: openpyxl worksheet
        cell: целевая ячейка (уже заполненная числовым default'ом)
        days_options: список int, например [10, 30, 60]
    """
    safe = ",".join(str(int(d)) for d in days_options)
    formula = f'"{safe}"'
    dv = DataValidation(
        type="list",
        formula1=formula,
        allow_blank=False,
        showDropDown=False,  # False = стрелка ВИДНА
    )
    dv.prompt = "Выберите срок поставки (дней)"
    dv.promptTitle = "Срок поставки"
    dv.add(cell)
    ws.add_data_validation(dv)


def add_stock_comment(cell, wh_list: list[dict]):
    """
    Добавляет Comment с детализацией по складам к ячейке остатка.

    Args:
        cell: openpyxl cell (уже содержит значение остатка)
        wh_list: [{warehouse_name, quantity, in_way_from_client}] — уже merged и отфильтрован
    """
    total_iwfc = sum(w.get('in_way_from_client', 0) for w in wh_list)
    active = [w for w in wh_list if w['quantity'] > 0]
    active.sort(key=lambda w: w['quantity'], reverse=True)

    if not active and total_iwfc <= 0:
        return

    detailed_lines = [f"{w['warehouse_name']}: {w['quantity']} шт" for w in active]
    detailed = "\n".join(detailed_lines) if detailed_lines else "нет"
    wh_total_qty = sum(w['quantity'] for w in active)
    comment_text = (
        f"Остатки по складам:\n{detailed}\n\n"
        f"Итого на складах: {wh_total_qty} шт"
    )
    if total_iwfc > 0:
        comment_text += f"\nВ возврате: {total_iwfc} шт"
    comment = Comment(comment_text, "WB Analiz")
    comment.width = 300
    comment.height = (len(active) + 8) * 14
    cell.comment = comment
