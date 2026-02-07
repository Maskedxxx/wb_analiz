"""
Настройки телеграм-бота.
"""

import os

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')  # ID чата заказчика

# Пути
WB_TOKEN_FILE = os.getenv('WB_TOKEN_FILE', '/app/nemov_token.txt')
FEEDBACK_DIR = os.getenv('FEEDBACK_DIR', '/app/feedback')
REPORTS_DIR = os.getenv('REPORTS_DIR', '/app/reports')
LOGS_DIR = os.getenv('LOGS_DIR', '/app/logs')

# Расписание
REPORT_TIME = "09:00"  # МСК
TIMEZONE = "Europe/Moscow"

# Пороги для групп товаров (шт/день)
THRESHOLD_A = 4.0   # A: ≥4 (ходовые)
THRESHOLD_B = 0.5   # B: ≥0.5, C: <0.5 (редкие)
