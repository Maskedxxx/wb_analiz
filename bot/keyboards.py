"""
Inline-клавиатуры для меню бота.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

from bot.utils.stores import store_display_name  # noqa: F401 — re-exported below


# === Callback Data ===

class MenuCB(CallbackData, prefix="menu"):
    action: str  # "analysis", "settings"


class StoreCB(CallbackData, prefix="store"):
    action: str     # "select", "last", "new", "edit_menu", "edit_name", "edit_token", "delete", "confirm_delete", "add"
    store_id: int = 0


class StorePageCB(CallbackData, prefix="storepage"):
    page: int = 0


class SettingsCB(CallbackData, prefix="settings"):
    action: str  # "time", "stores", "calc_params", "days_threshold", "group_thresholds", "refill_reserve", "refill_period", "warehouse_distrib"


class NavCB(CallbackData, prefix="nav"):
    target: str  # "main", "analysis", "settings", "store_mgmt", "calc_params"


class CompareCB(CallbackData, prefix="cmp"):
    action: str     # "select_first", "select_second"
    store_id: int = 0


class CompareModeCB(CallbackData, prefix="cmpmode"):
    action: str  # "pair" | "summary"


class SubscribeCB(CallbackData, prefix="sub"):
    action: str  # "toggle"


# === Keyboard Builders ===

def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню: Анализ + Настройки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Анализ остатков",
            callback_data=MenuCB(action="analysis").pack()
        )],
        [InlineKeyboardButton(
            text="🔀 Сравнение магазинов",
            callback_data=MenuCB(action="comparison").pack()
        )],
        [InlineKeyboardButton(
            text="⚙️ Настройки",
            callback_data=MenuCB(action="settings").pack()
        )],
    ])


def stores_list_kb(stores: list, action: str = "select") -> InlineKeyboardMarkup:
    """
    Список магазинов как кнопки.

    Args:
        stores: список dict с id и name
        action: "select" для анализа, "edit"/"delete" для управления
    """
    buttons = []
    for s in stores:
        buttons.append([InlineKeyboardButton(
            text=store_display_name(s),
            callback_data=StoreCB(action=action, store_id=s['id']).pack()
        )])

    if not stores:
        buttons.append([InlineKeyboardButton(
            text="Нет магазинов. Добавьте в настройках.",
            callback_data=NavCB(target="settings").pack()
        )])

    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavCB(target="main").pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def store_actions_kb(store_id: int, last_report_time: str = None) -> InlineKeyboardMarkup:
    """Действия с магазином: последний отчёт / новый отчёт."""
    buttons = []

    if last_report_time:
        buttons.append([InlineKeyboardButton(
            text=f"📄 Последний отчёт ({last_report_time})",
            callback_data=StoreCB(action="last", store_id=store_id).pack()
        )])

    buttons.append([InlineKeyboardButton(
        text="🔄 Сгенерировать новый отчёт",
        callback_data=StoreCB(action="new", store_id=store_id).pack()
    )])
    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavCB(target="analysis").pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_kb(current_time: str = "09:00", is_subscribed: bool = False) -> InlineKeyboardMarkup:
    """Меню настроек."""
    subscribe_text = "🔕 Отписаться от рассылки" if is_subscribed else "🔔 Подписаться на рассылку"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🕐 Время отчётов: {current_time}",
            callback_data=SettingsCB(action="time").pack()
        )],
        [InlineKeyboardButton(
            text="📐 Параметры расчёта",
            callback_data=SettingsCB(action="calc_params").pack()
        )],
        [InlineKeyboardButton(
            text="🏭 Склады поставок",
            callback_data=SettingsCB(action="warehouse_distrib").pack()
        )],
        [InlineKeyboardButton(
            text="🏪 Управление магазинами",
            callback_data=SettingsCB(action="stores").pack()
        )],
        [InlineKeyboardButton(
            text=subscribe_text,
            callback_data=SubscribeCB(action="toggle").pack()
        )],
        [InlineKeyboardButton(
            text="← Назад",
            callback_data=NavCB(target="main").pack()
        )],
    ])


def calc_params_kb(
    days_n: int = 7,
    threshold_a: float = 4.0,
    threshold_b: float = 0.5,
    threshold_c: float = 0.2,
    refill_reserve_pct: int = 20,
    refill_period_days: int = 30,
) -> InlineKeyboardMarkup:
    """Подменю параметров расчёта."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📅 Порог повышения цены: {days_n}д",
            callback_data=SettingsCB(action="days_threshold").pack()
        )],
        [InlineKeyboardButton(
            text=f"📦 Границы групп: A≥{threshold_a} · B≥{threshold_b} · D<{threshold_c}",
            callback_data=SettingsCB(action="group_thresholds").pack()
        )],
        [InlineKeyboardButton(
            text=f"➕ Запас пополнения остатков: {refill_reserve_pct}%",
            callback_data=SettingsCB(action="refill_reserve").pack()
        )],
        [InlineKeyboardButton(
            text=f"📆 Срок расчёта объёма: {refill_period_days}д",
            callback_data=SettingsCB(action="refill_period").pack()
        )],
        [InlineKeyboardButton(
            text="← Назад",
            callback_data=NavCB(target="settings").pack()
        )],
    ])


_STORE_PAGE_SIZE = 5


def store_management_kb(stores: list, page: int = 0) -> InlineKeyboardMarkup:
    """Управление магазинами: список с пагинацией + добавить."""
    total = len(stores)
    total_pages = max(1, (total + _STORE_PAGE_SIZE - 1) // _STORE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_stores = stores[page * _STORE_PAGE_SIZE:(page + 1) * _STORE_PAGE_SIZE]

    buttons = []
    for s in page_stores:
        buttons.append([InlineKeyboardButton(
            text=f"🏪 {store_display_name(s)}",
            callback_data=StoreCB(action="edit_menu", store_id=s['id']).pack()
        )])
        buttons.append([
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=StoreCB(action="edit_menu", store_id=s['id']).pack()
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=StoreCB(action="delete", store_id=s['id']).pack()
            ),
        ])

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀",
                callback_data=StorePageCB(page=page - 1).pack()
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=StorePageCB(page=page).pack()
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶",
                callback_data=StorePageCB(page=page + 1).pack()
            ))
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(
        text="➕ Добавить магазин",
        callback_data=StoreCB(action="add").pack()
    )])
    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavCB(target="settings").pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def store_edit_menu_kb(store_id: int) -> InlineKeyboardMarkup:
    """Подменю редактирования магазина: название / токен."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📝 Торговое название",
            callback_data=StoreCB(action="edit_name", store_id=store_id).pack()
        )],
        [InlineKeyboardButton(
            text="🔑 Токен API",
            callback_data=StoreCB(action="edit_token", store_id=store_id).pack()
        )],
        [InlineKeyboardButton(
            text="← Назад к списку",
            callback_data=NavCB(target="store_mgmt").pack()
        )],
    ])


def confirm_delete_kb(store_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления магазина."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=StoreCB(action="confirm_delete", store_id=store_id).pack()
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=NavCB(target="store_mgmt").pack()
            ),
        ]
    ])


def comparison_mode_kb() -> InlineKeyboardMarkup:
    """Подменю режима сравнения: пара или сводный."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔀 Сравнение пары",
            callback_data=CompareModeCB(action="pair").pack()
        )],
        [InlineKeyboardButton(
            text="📋 Сводный отчёт",
            callback_data=CompareModeCB(action="summary").pack()
        )],
        [InlineKeyboardButton(
            text="← Назад",
            callback_data=NavCB(target="main").pack()
        )],
    ])


def compare_stores_kb(stores: list, action: str = "select_first", exclude_id: int = None) -> InlineKeyboardMarkup:
    """
    Список магазинов для сравнения.

    Args:
        stores: список dict с id и name
        action: "select_first" или "select_second"
        exclude_id: id магазина для исключения из списка (уже выбранный)
    """
    buttons = []
    for s in stores:
        if exclude_id and s['id'] == exclude_id:
            continue
        buttons.append([InlineKeyboardButton(
            text=store_display_name(s),
            callback_data=CompareCB(action=action, store_id=s['id']).pack()
        )])

    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavCB(target="main").pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены (возврат в главное меню)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=NavCB(target="main").pack()
        )]
    ])


def cancel_to_store_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены (возврат к списку магазинов)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=NavCB(target="store_mgmt").pack()
        )]
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню (после завершения операции)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="← Главное меню",
            callback_data=NavCB(target="main").pack()
        )]
    ])
