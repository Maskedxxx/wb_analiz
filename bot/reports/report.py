"""
Фасад обратной совместимости для модуля отчётов.

Все функции перенесены в отдельные модули:
- bot.reports.excel_styles — константы стилей и форматирование Excel
- bot.services.calculations — бизнес-логика (группы, остатки, цены)
- bot.services.data_service — загрузка данных из API и кэширование
- bot.reports.single — отчёт по одному магазину
- bot.reports.comparison — сравнительный отчёт (два магазина)
- bot.reports.summary — сводный отчёт (все магазины)
"""

# Бизнес-логика
from bot.services.calculations import (  # noqa: F401
    assign_group,
    calc_avg_by_group,
    calc_days_remaining,
    get_price_increase,
    aggregate_by_article,
)

# Загрузка данных
from bot.services.data_service import (  # noqa: F401
    fetch_store_data,
    fetch_warehouse_data,
)

# Генерация отчётов
from bot.reports.single import generate_report_from_data  # noqa: F401
from bot.reports.comparison import generate_comparison_report  # noqa: F401
from bot.reports.summary import generate_summary_report  # noqa: F401
