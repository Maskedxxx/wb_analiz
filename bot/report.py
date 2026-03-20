"""
Генерация Excel-отчёта с рекомендациями по ценам.

Логика:
1. Загрузка данных (30д, 14д, 7д) из WB API
2. Группировка товаров (A/B/C) по средним продажам
3. Расчёт avg_per_day по периоду группы
4. Расчёт days_remaining (на сколько дней хватит остатка)
5. Шкала повышения цены
6. Формирование Excel с 2 листами
"""

import os
import re
import logging
from datetime import datetime

import pytz

import pandas as pd
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# Настройка логирования
logger = logging.getLogger(__name__)

from wb_api import get_orders, get_stocks, get_prices, merge_orders_stocks, calc_avg_per_day
from bot.config import THRESHOLD_A, THRESHOLD_B, REPORTS_DIR

# ── Цветовые константы ────────────────────────────────────────────────────────

# Шапка таблицы
HEADER_BG = "2E4057"
HEADER_FG = "FFFFFF"

# Цвета групп (фон ячейки)
GROUP_COLORS = {
    "A": "B7E4C7",  # мятный зелёный
    "B": "FFD6A5",  # персиковый
    "C": "C8B6E2",  # лавандовый
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
WB_CABINET_URL = "https://www.wildberries.ru/catalog/{}/detail.aspx"

# ── Вспомогательные стили ─────────────────────────────────────────────────────

def _thin_border(color="CCCCCC"):
    side = Side(style="thin", color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def _fill(hex_color):
    return PatternFill(fill_type="solid", fgColor=hex_color)


# ── Логика группировки и расчётов ─────────────────────────────────────────────

def assign_group(avg_per_day: float, threshold_a: float = THRESHOLD_A, threshold_b: float = THRESHOLD_B) -> str:
    """
    Определяет группу товара по средним продажам в день.

    A: ≥threshold_a шт/день (ходовые) — анализ за 7 дней
    B: ≥threshold_b шт/день — анализ за 14 дней
    C: <threshold_b шт/день (редкие) — анализ за 30 дней
    """
    if avg_per_day >= threshold_a:
        return 'A'
    elif avg_per_day >= threshold_b:
        return 'B'
    else:
        return 'C'


def calc_avg_by_group(row) -> float:
    """
    Возвращает среднее продаж в день по периоду группы.

    A: по 7 дням
    B: по 14 дням
    C: по 30 дням
    """
    if row['group'] == 'A':
        return row['orders_count_7d'] / 7 if pd.notna(row['orders_count_7d']) else 0
    elif row['group'] == 'B':
        return row['orders_count_14d'] / 14 if pd.notna(row['orders_count_14d']) else 0
    else:  # C
        return row['avg_per_day_30d']


def calc_days_remaining(row) -> float:
    """
    На сколько дней хватит остатка.

    Returns:
        None если нет продаж, иначе кол-во дней
    """
    if row['avg_per_day'] == 0:
        return None
    return row['stock_qty'] / row['avg_per_day']


def get_price_increase(days_remaining: float, days_threshold: int = 7) -> int:
    """
    Возвращает % повышения цены по шкале.

    Шкала:
    - > days_threshold дней: 0%
    - 6-7 дней: 5%
    - 5-6 дней: 10%
    - 4-5 дней: 15%
    - 3-4 дней: 25%
    - 2-3 дней: 30%
    - 1-2 дней: 40%
    - < 1 дня: 50%
    """
    if days_remaining is None or days_remaining > days_threshold:
        return 0
    elif days_remaining >= 6:
        return 5
    elif days_remaining >= 5:
        return 10
    elif days_remaining >= 4:
        return 15
    elif days_remaining >= 3:
        return 25
    elif days_remaining >= 2:
        return 30
    elif days_remaining >= 1:
        return 40
    else:
        return 50


# ── Форматирование Excel ──────────────────────────────────────────────────────

def apply_header_style(ws, column_widths: dict):
    """Тёмная шапка, фриз, авто-фильтр, высота строк, ширина столбцов."""
    header_font = Font(name="Arial", size=11, bold=True, color=HEADER_FG)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 34
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = _fill(HEADER_BG)
        cell.alignment = center
        cell.border = _thin_border("444444")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width


def apply_data_style(ws, float_cols: list, int_cols: list):
    """Шрифт, выравнивание, высота строк, числовые форматы для строк с данными."""
    data_font = Font(name="Arial", size=10, color="1A1A2E")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    border = _thin_border()

    for row in ws.iter_rows(min_row=2):
        # пропускаем строки аннотаций (нет значения во 2-м столбце)
        if row[0].value is None:
            continue
        ws.row_dimensions[row[0].row].height = 16
        for cell in row:
            cell.font = data_font
            cell.border = border
            cell.alignment = left if cell.column == 1 else center
            if cell.column in float_cols:
                cell.number_format = "0.00"
            elif cell.column in int_cols:
                cell.number_format = "0"


def apply_group_colors(ws, group_col: int):
    """Окрашивает только ячейку группы товара."""
    for row in ws.iter_rows(min_row=2):
        cell = row[group_col - 1]
        group = cell.value
        if group in GROUP_COLORS:
            cell.fill = _fill(GROUP_COLORS[group])
            cell.font = Font(name="Arial", size=10, bold=True, color="1A1A2E")


def apply_price_increase_colors(ws, pct_col: int):
    """Градиент фона + контрастный текст для ячейки % повышения."""
    for row in ws.iter_rows(min_row=2):
        cell = row[pct_col - 1]
        pct = cell.value
        if pct in PRICE_INCREASE_COLORS:
            bg, fg = PRICE_INCREASE_COLORS[pct]
            cell.fill = _fill(bg)
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
    if has_threshold_row:
        ws.cell(row=start_row + 4, column=1).font = note_font

    # Итоговые строки листа 2 (на 4 строки выше start_row: пустая + 2 итога + пустая)
    summary_row = start_row - 4
    if summary_row >= 1:
        ws.cell(row=summary_row, column=1).font = summary_font
        ws.cell(row=summary_row + 1, column=1).font = summary_font


def apply_hyperlinks(ws, link_col: int):
    """Превращает nmId в кликабельные ссылки на кабинет WB."""
    hyperlink_font = Font(name="Arial", size=10, color="1155CC", underline="single")
    center = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=2):
        cell = row[link_col - 1]
        nm_id = cell.value
        if nm_id is not None:
            url = WB_CABINET_URL.format(nm_id)
            cell.hyperlink = url
            cell.value = nm_id
            cell.font = hyperlink_font
            cell.alignment = center


# ── Загрузка данных из API ────────────────────────────────────────────────────

def fetch_store_data(
    token: str = None,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
) -> list[dict]:
    """
    Загружает данные из WB API, рассчитывает метрики.

    Returns:
        Список словарей — по одному на каждый товар (nm_id).
    """
    logger.info("=== Загрузка данных из WB API ===")

    # === 1. Загрузка данных за 30 дней ===
    try:
        logger.info("Загрузка заказов за 30 дней...")
        orders_30d = get_orders(30, token=token)
        logger.info(f"✓ Заказы 30д: {len(orders_30d)} записей")
    except Exception as e:
        logger.error(f"✗ Ошибка загрузки заказов 30д: {e}")
        raise

    try:
        logger.info("Загрузка остатков...")
        stocks = get_stocks(orders_30d['nmId'].tolist(), token=token)
        logger.info(f"✓ Остатки: {len(stocks)} записей")
    except Exception as e:
        logger.error(f"✗ Ошибка загрузки остатков: {e}")
        raise

    # Объединяем заказы и остатки
    df = merge_orders_stocks(orders_30d, stocks)
    df = calc_avg_per_day(df, days=30)

    # Заполняем поля возвратов если отсутствуют после merge
    for col in ['in_way_from_client', 'stock_qty_clean']:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    # Используем чистый остаток (без товаров в возврате) для расчётов
    df['stock_qty_original'] = df['stock_qty']
    df['stock_qty'] = df['stock_qty_clean']

    logger.info(f"Объединено товаров: {len(df)}")

    # === 2. Группировка товаров (A/B/C) ===
    df['group'] = df['avg_per_day_30d'].apply(lambda x: assign_group(x, threshold_a, threshold_b))

    # === 3. Загрузка данных за 7 и 14 дней ===
    try:
        logger.info("Загрузка заказов за 7 дней...")
        orders_7d = get_orders(7, token=token)
        orders_7d = orders_7d[['nmId', 'orders_count_7d']]
        logger.info(f"✓ Заказы 7д: {len(orders_7d)} записей")
    except Exception as e:
        logger.error(f"✗ Ошибка загрузки заказов 7д: {e}")
        raise

    try:
        logger.info("Загрузка заказов за 14 дней...")
        orders_14d = get_orders(14, token=token)
        orders_14d = orders_14d[['nmId', 'orders_count_14d']]
        logger.info(f"✓ Заказы 14д: {len(orders_14d)} записей")
    except Exception as e:
        logger.error(f"✗ Ошибка загрузки заказов 14д: {e}")
        raise

    # Присоединяем к основной таблице
    df = df.merge(orders_7d, on='nmId', how='left')
    df = df.merge(orders_14d, on='nmId', how='left')

    # === 4. Расчёт среднего по группе ===
    df['avg_per_day'] = df.apply(calc_avg_by_group, axis=1)

    # === 5. Расчёт days_remaining ===
    df['days_remaining'] = df.apply(calc_days_remaining, axis=1)

    # === 6. Расчёт % повышения цены ===
    df['price_increase_pct'] = df['days_remaining'].apply(lambda d: get_price_increase(d, days_threshold))

    # === 7. Загрузка цен ===
    try:
        logger.info("Загрузка цен...")
        prices_map = get_prices(df['nmId'].tolist(), token=token)
        df['price'] = df['nmId'].map(prices_map)
        logger.info(f"✓ Цены загружены: {len(prices_map)} из {len(df)} товаров")
    except Exception as e:
        logger.warning(f"Не удалось загрузить цены: {e}")
        df['price'] = None

    logger.info("=== Данные загружены и рассчитаны ===")

    # Конвертируем в list[dict] для сохранения в БД
    result = []
    for _, row in df.iterrows():
        result.append({
            'nm_id': int(row['nmId']),
            'supplier_article': row.get('supplierArticle'),
            'subject': row.get('subject'),
            'category': row.get('category'),
            'product_group': row['group'],
            'stock_qty': int(row['stock_qty']),
            'in_way_from_client': int(row['in_way_from_client']),
            'stock_qty_clean': int(row['stock_qty_clean']),
            'orders_7d': int(row['orders_count_7d']) if pd.notna(row.get('orders_count_7d')) else None,
            'orders_14d': int(row['orders_count_14d']) if pd.notna(row.get('orders_count_14d')) else None,
            'orders_30d': int(row['orders_count_30d']),
            'avg_per_day': round(row['avg_per_day'], 4),
            'days_remaining': round(row['days_remaining'], 2) if row['days_remaining'] is not None else None,
            'price_increase_pct': int(row['price_increase_pct']),
            'price': float(row['price']) if pd.notna(row.get('price')) else None,
        })

    return result


# ── Генерация Excel из данных ────────────────────────────────────────────────

def generate_report_from_data(
    product_rows: list[dict],
    store_name: str = None,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
) -> str:
    """
    Генерирует Excel-отчёт из готовых данных (без обращения к API).

    Args:
        product_rows: список словарей с данными товаров (из БД или fetch_store_data)
        store_name: имя магазина для имени файла
        days_threshold: порог дней остатка (для аннотаций)
        threshold_a: порог группы A (для аннотаций)
        threshold_b: порог группы B (для аннотаций)

    Returns:
        Путь к сгенерированному файлу
    """
    logger.info("=== Генерация Excel-отчёта ===")

    df = pd.DataFrame(product_rows)

    if df.empty:
        logger.warning("Нет данных для отчёта")
        # Создаём пустой отчёт
        df = pd.DataFrame(columns=[
            'nm_id', 'supplier_article', 'subject', 'category',
            'product_group', 'stock_qty', 'in_way_from_client', 'stock_qty_clean',
            'orders_7d', 'orders_14d', 'orders_30d',
            'avg_per_day', 'days_remaining', 'price_increase_pct',
        ])

    # Лист 1: Товары для повышения цены (есть остаток И нужно повышение)
    report = df[(df['stock_qty'] > 0) & (df['price_increase_pct'] > 0)].copy()
    report = report.sort_values('days_remaining')
    logger.info(f"Товаров для повышения цены: {len(report)}")

    # Лист 2: Товары с нулевым остатком
    out_of_stock = df[df['stock_qty'] == 0].copy()
    out_of_stock = out_of_stock.sort_values(['product_group', 'avg_per_day'], ascending=[True, False])
    logger.info(f"Товаров с нулевым остатком: {len(out_of_stock)}")

    # Сохранение Excel
    os.makedirs(REPORTS_DIR, exist_ok=True)

    timestamp = datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y%m%d_%H%M')
    safe_name = re.sub(r'[^\w\s-]', '', store_name).strip()[:50] if store_name else ""
    name_part = f"_{safe_name}" if safe_name else ""
    output_path = os.path.join(REPORTS_DIR, f'price_report{name_part}_{timestamp}.xlsx')

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # ── Лист 1: Повысить цену ──────────────────────────────────────────
        report_export = report[[
            'supplier_article', 'nm_id', 'product_group',
            'stock_qty', 'in_way_from_client',
            'avg_per_day', 'days_remaining', 'price_increase_pct', 'price'
        ]].copy()
        report_export.columns = [
            'Артикул', 'ID (WB)', 'Группа',
            'Остаток (чист.)', 'В возвратах',
            'Продаж/день', 'Дней осталось', 'Повышение %', 'Цена ₽'
        ]
        report_export.to_excel(writer, sheet_name='Повысить цену', index=False)

        # ── Лист 2: Нет на складе ─────────────────────────────────────────
        out_of_stock_export = out_of_stock[[
            'supplier_article', 'nm_id', 'product_group', 'avg_per_day', 'price'
        ]].copy()
        out_of_stock_export.columns = ['Артикул', 'ID (WB)', 'Группа', 'Продаж/день', 'Цена ₽']
        out_of_stock_export.to_excel(writer, sheet_name='Нет на складе', index=False)

        # Итоги внизу листа 2
        ws2 = writer.sheets['Нет на складе']
        last_row = len(out_of_stock_export) + 3
        ws2.cell(row=last_row, column=1, value=f'Товаров с нулевым остатком: {len(out_of_stock)}')
        ws2.cell(row=last_row + 1, column=1, value=f'Упущенные продажи в день: {out_of_stock["avg_per_day"].sum():.2f} шт')

        # Форматирование
        logger.info("Форматирование Excel...")

        ws1 = writer.sheets['Повысить цену']

        # Лист 1
        apply_header_style(ws1, {1: 24, 2: 15, 3: 11, 4: 17, 5: 15, 6: 15, 7: 17, 8: 15, 9: 13})
        apply_data_style(ws1, float_cols=[6, 7, 9], int_cols=[4, 5, 8])
        apply_hyperlinks(ws1, link_col=2)
        apply_group_colors(ws1, group_col=3)
        apply_price_increase_colors(ws1, pct_col=8)

        # Лист 2
        apply_header_style(ws2, {1: 24, 2: 15, 3: 11, 4: 15, 5: 13})
        apply_data_style(ws2, float_cols=[4, 5], int_cols=[])
        apply_hyperlinks(ws2, link_col=2)
        apply_group_colors(ws2, group_col=3)

        # Аннотации под таблицами
        ws1_last = len(report_export) + 4
        ws1.cell(row=ws1_last, column=1, value='— Группы товаров —')
        ws1.cell(row=ws1_last + 1, column=1, value=f'A: ходовые (≥{threshold_a} шт/день за 30д) → среднее по 7 дням')
        ws1.cell(row=ws1_last + 2, column=1, value=f'B: средние (≥{threshold_b} шт/день) → среднее по 14 дням')
        ws1.cell(row=ws1_last + 3, column=1, value=f'C: редкие (<{threshold_b} шт/день) → среднее по 30 дням')
        ws1.cell(row=ws1_last + 4, column=1, value=f'Порог повышения цены: ≤{days_threshold} дней остатка')
        apply_legend_style(ws1, ws1_last, has_threshold_row=True)

        ws2_last = last_row + 4
        ws2.cell(row=ws2_last, column=1, value='— Группы товаров —')
        ws2.cell(row=ws2_last + 1, column=1, value=f'A: ходовые (≥{threshold_a} шт/день за 30д)')
        ws2.cell(row=ws2_last + 2, column=1, value=f'B: средние (≥{threshold_b} шт/день)')
        ws2.cell(row=ws2_last + 3, column=1, value=f'C: редкие (<{threshold_b} шт/день)')
        apply_legend_style(ws2, ws2_last, has_threshold_row=False)

    logger.info(f"✓ Отчёт сохранён: {output_path}")
    logger.info("=== Генерация завершена ===")

    return output_path


# ── Сравнительный отчёт ──────────────────────────────────────────────────────

# Цвета рекомендаций сравнения
CMP_RAISE_BG = "E8F5E9"   # светло-зелёный
CMP_LOWER_BG = "FFEBEE"   # светло-красный
CMP_PAIR_ALT_BG = "F5F5F5"  # чередование пар


def generate_comparison_report(
    store1_data: list[dict],
    store2_data: list[dict],
    store1_name: str,
    store2_name: str,
    days_threshold: int = 7,
    threshold_a: float = THRESHOLD_A,
    threshold_b: float = THRESHOLD_B,
) -> str | None:
    """
    Генерирует сравнительный Excel-отчёт по двум магазинам.

    Сопоставляет товары по supplier_article. Для каждой пары показывает
    данные обоих магазинов и рекомендацию по цене.

    Returns:
        Путь к файлу или None если нет совпадающих позиций.
    """
    from openpyxl import Workbook

    logger.info(f"=== Сравнительный отчёт: {store1_name} vs {store2_name} ===")

    # Группировка по supplier_article (агрегация дублей)
    def aggregate_by_article(rows: list[dict]) -> dict:
        result = {}
        for r in rows:
            art = r.get('supplier_article')
            if not art:
                continue
            if art not in result:
                result[art] = r.copy()
            else:
                # Суммируем остатки и продажи по всем nmId одного артикула
                existing = result[art]
                existing['stock_qty'] = existing.get('stock_qty', 0) + r.get('stock_qty', 0)
                existing['stock_qty_clean'] = existing.get('stock_qty_clean', 0) + r.get('stock_qty_clean', 0)
                existing['avg_per_day'] = (existing.get('avg_per_day') or 0) + (r.get('avg_per_day') or 0)
                # nm_id / price — берём от варианта с наибольшими продажами
                if (r.get('avg_per_day') or 0) > (existing.get('_max_avg') or 0):
                    existing['_max_avg'] = r.get('avg_per_day') or 0
                    existing['nm_id'] = r.get('nm_id')
                    existing['price'] = r.get('price')

        # Пересчитываем days_remaining и группу после агрегации
        for item in result.values():
            avg = item.get('avg_per_day') or 0
            item['days_remaining'] = (item['stock_qty'] / avg) if avg > 0 else None
            item['product_group'] = assign_group(avg)
            item.pop('_max_avg', None)
        return result

    agg1 = aggregate_by_article(store1_data)
    agg2 = aggregate_by_article(store2_data)

    # Общие артикулы
    common_articles = sorted(set(agg1.keys()) & set(agg2.keys()))
    only_s1 = len(set(agg1.keys()) - set(agg2.keys()))
    only_s2 = len(set(agg2.keys()) - set(agg1.keys()))

    logger.info(f"Совпадений: {len(common_articles)}, только в маг.1: {only_s1}, только в маг.2: {only_s2}")

    if not common_articles:
        return None

    # Создаём Excel вручную (для merged cells)
    wb = Workbook()
    ws = wb.active
    ws.title = "Сравнение"

    # Шапка
    headers = ['Артикул', 'Магазин', 'ID (WB)', 'Остаток', 'Дней осталось',
               'Продаж/день', 'Группа', 'Цена ₽', 'Рекомендация']
    col_widths = {1: 22, 2: 24, 3: 15, 4: 12, 5: 16, 6: 15, 7: 11, 8: 13, 9: 18}

    header_font = Font(name="Arial", size=11, bold=True, color=HEADER_FG)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = _fill(HEADER_BG)
        cell.alignment = header_align
        cell.border = _thin_border("444444")

    ws.freeze_panes = "A2"
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    ws.row_dimensions[1].height = 34

    # Стили данных
    data_font = Font(name="Arial", size=10, color="1A1A2E")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    hyperlink_font = Font(name="Arial", size=10, color="1155CC", underline="single")
    inner_thin = Side(style="thin", color="CCCCCC")
    pair_thick = Side(style="medium", color="888888")

    def _pair_border(is_top_row, col_idx, num_cols):
        """Рамка ячейки внутри пары: толстая снаружи, тонкая между строками."""
        top = pair_thick if is_top_row else inner_thin
        bottom = pair_thick if not is_top_row else inner_thin
        l = pair_thick if col_idx == 1 else inner_thin
        r = pair_thick if col_idx == num_cols else inner_thin
        return Border(left=l, right=r, top=top, bottom=bottom)

    num_cols = len(headers)
    current_row = 2

    for pair_idx, article in enumerate(common_articles):
        s1 = agg1[article]
        s2 = agg2[article]

        # Определяем рекомендацию
        avg1 = s1.get('avg_per_day') or 0
        avg2 = s2.get('avg_per_day') or 0
        max_avg = max(avg1, avg2)

        if max_avg == 0:
            rec1, rec2 = "—", "—"
        elif abs(avg1 - avg2) / max_avg < 0.1:
            rec1, rec2 = "—", "—"
        elif avg1 > avg2:
            rec1, rec2 = "↑ Повысить", "↓ Понизить"
        else:
            rec1, rec2 = "↓ Понизить", "↑ Повысить"

        row1 = current_row
        row2 = current_row + 1

        # Чередование фона пар
        pair_bg = CMP_PAIR_ALT_BG if pair_idx % 2 == 1 else None

        for row_num, store_data, store_name, rec, is_top in [
            (row1, s1, store1_name, rec1, True),
            (row2, s2, store2_name, rec2, False),
        ]:
            ws.row_dimensions[row_num].height = 18

            # B: Магазин
            c = ws.cell(row=row_num, column=2, value=store_name)
            c.font = data_font
            c.alignment = left
            c.border = _pair_border(is_top, 2, num_cols)

            # C: ID (WB) — гиперссылка
            nm_id = store_data.get('nm_id')
            c = ws.cell(row=row_num, column=3, value=nm_id)
            if nm_id:
                c.hyperlink = WB_CABINET_URL.format(nm_id)
                c.font = hyperlink_font
            else:
                c.font = data_font
            c.alignment = center
            c.border = _pair_border(is_top, 3, num_cols)

            # D: Остаток
            c = ws.cell(row=row_num, column=4, value=store_data.get('stock_qty', 0))
            c.font = data_font
            c.alignment = center
            c.border = _pair_border(is_top, 4, num_cols)
            c.number_format = "0"

            # E: Дней осталось
            dr = store_data.get('days_remaining')
            c = ws.cell(row=row_num, column=5, value=dr)
            c.font = data_font
            c.alignment = center
            c.border = _pair_border(is_top, 5, num_cols)
            if dr is not None:
                c.number_format = "0.0"

            # F: Продаж/день
            c = ws.cell(row=row_num, column=6, value=store_data.get('avg_per_day', 0))
            c.font = data_font
            c.alignment = center
            c.border = _pair_border(is_top, 6, num_cols)
            c.number_format = "0.00"

            # G: Группа
            group = store_data.get('product_group', '')
            c = ws.cell(row=row_num, column=7, value=group)
            c.font = Font(name="Arial", size=10, bold=True, color="1A1A2E")
            c.alignment = center
            c.border = _pair_border(is_top, 7, num_cols)
            if group in GROUP_COLORS:
                c.fill = _fill(GROUP_COLORS[group])

            # H: Цена
            price = store_data.get('price')
            c = ws.cell(row=row_num, column=8, value=price)
            c.font = data_font
            c.alignment = center
            c.border = _pair_border(is_top, 8, num_cols)
            if price is not None:
                c.number_format = "0.00"

            # I: Рекомендация
            c = ws.cell(row=row_num, column=9, value=rec)
            c.font = Font(name="Arial", size=10, bold=True, color="1A1A2E")
            c.alignment = center
            c.border = _pair_border(is_top, 9, num_cols)
            if "Повысить" in rec:
                c.fill = _fill(CMP_RAISE_BG)
            elif "Понизить" in rec:
                c.fill = _fill(CMP_LOWER_BG)

            # Фон чередования
            if pair_bg:
                for col in range(2, num_cols + 1):
                    existing = ws.cell(row=row_num, column=col)
                    if existing.fill == PatternFill():
                        existing.fill = _fill(pair_bg)

        # A: Артикул (merged) с толстой рамкой
        ws.merge_cells(start_row=row1, start_column=1, end_row=row2, end_column=1)
        c = ws.cell(row=row1, column=1, value=article)
        c.font = Font(name="Arial", size=10, bold=True, color="1A1A2E")
        c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        c.border = Border(left=pair_thick, right=inner_thin, top=pair_thick, bottom=pair_thick)
        ws.cell(row=row2, column=1).border = Border(
            left=pair_thick, right=inner_thin, top=inner_thin, bottom=pair_thick,
        )

        current_row += 2

    # Итоги внизу
    summary_row = current_row + 1
    summary_font = Font(name="Arial", size=9, bold=True, color="555555")

    ws.cell(row=summary_row, column=1, value=f"Совпадающих позиций: {len(common_articles)}").font = summary_font
    ws.cell(row=summary_row + 1, column=1, value=f"Только в {store1_name}: {only_s1}").font = summary_font
    ws.cell(row=summary_row + 2, column=1, value=f"Только в {store2_name}: {only_s2}").font = summary_font

    # Легенда
    legend_row = summary_row + 4
    title_font = Font(name="Arial", size=9, bold=True, color="888888")
    row_font = Font(name="Arial", size=9, italic=True, color="999999")

    ws.cell(row=legend_row, column=1, value="— Группы товаров —").font = title_font
    ws.cell(row=legend_row + 1, column=1,
            value=f"A: ходовые (≥{threshold_a} шт/день) → среднее по 7 дням").font = row_font
    ws.cell(row=legend_row + 2, column=1,
            value=f"B: средние (≥{threshold_b} шт/день) → среднее по 14 дням").font = row_font
    ws.cell(row=legend_row + 3, column=1,
            value=f"C: редкие (<{threshold_b} шт/день) → среднее по 30 дням").font = row_font

    ws.cell(row=legend_row + 5, column=1, value="— Рекомендации —").font = title_font
    ws.cell(row=legend_row + 6, column=1,
            value="↑ Повысить — товар продаётся лучше конкурента (можно повысить цену)").font = row_font
    ws.cell(row=legend_row + 7, column=1,
            value="↓ Понизить — товар отстаёт (снизить цену для стимуляции спроса)").font = row_font
    ws.cell(row=legend_row + 8, column=1,
            value="— паритет (разница продаж < 10%)").font = row_font

    # Сохранение — короткие имена для файла (только бренд или первое слово)
    def _short_name(full_name):
        if not full_name:
            return "store"
        # Берём часть до скобки: "DobroDom (ИП ...)" → "DobroDom"
        short = full_name.split('(')[0].strip()
        if not short:
            short = full_name.split()[0] if full_name.split() else "store"
        return re.sub(r'[^\w-]', '', short).strip()[:20]

    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y%m%d_%H%M')
    output_path = os.path.join(
        REPORTS_DIR,
        f'comparison_{_short_name(store1_name)}_{_short_name(store2_name)}_{timestamp}.xlsx',
    )

    wb.save(output_path)
    logger.info(f"✓ Сравнительный отчёт: {output_path}")
    return output_path
