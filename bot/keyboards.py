"""
Inline-клавиатуры для меню бота.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData


# === Callback Data ===

class MenuCB(CallbackData, prefix="menu"):
    action: str  # "analysis", "settings"


class StoreCB(CallbackData, prefix="store"):
    action: str     # "select", "last", "new", "edit", "delete", "confirm_delete", "add"
    store_id: int = 0


class SettingsCB(CallbackData, prefix="settings"):
    action: str  # "time", "stores"


class NavCB(CallbackData, prefix="nav"):
    target: str  # "main", "analysis", "settings", "store_mgmt", "calc_params"


class CompareCB(CallbackData, prefix="cmp"):
    action: str     # "select_first", "select_second"
    store_id: int = 0


class SubscribeCB(CallbackData, prefix="sub"):
    action: str  # "toggle"


# === Helpers ===

def store_display_name(store: dict) -> str:
    """'Бренд (ИП)' если задано marketplace_name, иначе просто name."""
    legal = store.get('name') or f"Магазин #{store['id']}"
    brand = store.get('marketplace_name')
    return f"{brand} ({legal})" if brand else legal


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


def calc_params_kb(days_n: int = 7, threshold_a: float = 4.0, threshold_b: float = 0.5) -> InlineKeyboardMarkup:
    """Подменю параметров расчёта."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📅 Порог дней: {days_n}",
            callback_data=SettingsCB(action="days_threshold").pack()
        )],
        [InlineKeyboardButton(
            text=f"📦 Группы: A≥{threshold_a} · B≥{threshold_b}",
            callback_data=SettingsCB(action="group_thresholds").pack()
        )],
        [InlineKeyboardButton(
            text="← Назад",
            callback_data=NavCB(target="settings").pack()
        )],
    ])


def store_management_kb(stores: list) -> InlineKeyboardMarkup:
    """Управление магазинами: список + добавить."""
    buttons = []
    for s in stores:
        buttons.append([
            InlineKeyboardButton(
                text=f"🏪 {store_display_name(s)}",
                callback_data=StoreCB(action="edit", store_id=s['id']).pack()
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=StoreCB(action="delete", store_id=s['id']).pack()
            ),
        ])

    buttons.append([InlineKeyboardButton(
        text="➕ Добавить магазин",
        callback_data=StoreCB(action="add").pack()
    )])
    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavCB(target="settings").pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню (после завершения операции)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="← Главное меню",
            callback_data=NavCB(target="main").pack()
        )]
    ])
