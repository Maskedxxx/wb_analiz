"""
Настройки телеграм-бота.
"""

import os
from zoneinfo import ZoneInfo

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')  # ID чата заказчика

# Авторизация
BOT_PASSWORD = os.getenv('BOT_PASSWORD', '')

# Пути
FEEDBACK_DIR = os.getenv('FEEDBACK_DIR', '/app/feedback')
REPORTS_DIR = os.getenv('REPORTS_DIR', '/app/reports')
LOGS_DIR = os.getenv('LOGS_DIR', '/app/logs')

# Расписание (значения по умолчанию, перекрываются из БД)
REPORT_TIME = "09:00"  # МСК
TIMEZONE = "Europe/Moscow"
MSK_TZ = ZoneInfo(TIMEZONE)

# Пороги и дефолты для настроек (единственный источник правды)
DEFAULT_DAYS_N = 7

# Фидбек
FEEDBACK_RETENTION_MONTHS = int(os.getenv('FEEDBACK_RETENTION_MONTHS', '3'))

# Отчёты
REPORT_RETENTION_DAYS = int(os.getenv('REPORT_RETENTION_DAYS', '30'))

# Логи
LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '90'))

# Пороги для групп товаров (шт/день)
THRESHOLD_A = 4.0   # A: ≥4 (ходовые)
THRESHOLD_B = 0.5   # B: ≥0.5, C: <0.5 (редкие)
THRESHOLD_C = 0.2   # C: ≥0.2 (редкие), D: <0.2 (почти не продаются)

# Кэш данных API (минуты) — если данные свежее, повторный запрос к API не делается
DATA_CACHE_TTL = int(os.getenv('DATA_CACHE_TTL', '30'))
