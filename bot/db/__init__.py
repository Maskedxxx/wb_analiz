"""
Пакет работы с БД. Реэкспорт всех публичных функций для обратной совместимости.

Использование: from bot.db import get_stores, get_setting, ...
"""

from bot.db.migrations import init_db, migrate_trademarks  # noqa: F401
from bot.db.stores import add_store, get_stores, get_store, update_store, delete_store  # noqa: F401
from bot.db.settings import get_setting, set_setting  # noqa: F401
from bot.db.reports import save_report_history, get_last_report, get_last_reports_batch, cleanup_old_reports  # noqa: F401
from bot.db.subscribers import add_subscriber, remove_subscriber, get_subscribers, is_subscriber  # noqa: F401
from bot.db.auth import is_authorized, authorize_user  # noqa: F401
from bot.db.products import (  # noqa: F401
    save_product_data, get_latest_product_data, is_data_fresh,
)
from bot.db.warehouse import (  # noqa: F401
    save_warehouse_data, get_latest_warehouse_data, is_warehouse_data_fresh,
)
from bot.db.audit import log_action  # noqa: F401
