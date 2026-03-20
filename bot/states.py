"""
FSM-стейты для навигации по меню бота.
"""

from aiogram.fsm.state import StatesGroup, State


class MenuStates(StatesGroup):
    """Состояния меню бота."""
    waiting_password = State()
    main = State()
    analysis_select_store = State()
    analysis_store_actions = State()
    settings = State()
    store_management = State()
    add_store_token = State()
    edit_store_name = State()
    set_report_time = State()
    set_days_threshold = State()
    set_group_thresholds = State()
