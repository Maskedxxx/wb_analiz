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
    edit_store_token = State()
    set_report_time = State()
    set_days_threshold = State()
    set_group_thresholds = State()
    set_refill_reserve = State()
    set_refill_period = State()
    comparison_mode = State()
    compare_select_first = State()
    compare_select_second = State()
    refill_distrib_enter = State()
    refill_distrib_confirm = State()
