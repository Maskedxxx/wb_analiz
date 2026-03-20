"""
Настройки: время отчётов, параметры расчёта.
"""

import re
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.keyboards import MenuCB, SettingsCB, NavCB, SubscribeCB, settings_kb, calc_params_kb, cancel_kb
from bot.states import MenuStates
from bot.config import REPORT_TIME as DEFAULT_REPORT_TIME, DEFAULT_DAYS_N, THRESHOLD_A as DEFAULT_THRESHOLD_A, THRESHOLD_B as DEFAULT_THRESHOLD_B
from bot.db import get_setting, set_setting, is_subscriber, add_subscriber, remove_subscriber
from bot.scheduler import reschedule_daily_reports

logger = logging.getLogger(__name__)

router = Router()


async def _send_settings(callback: CallbackQuery):
    """Показывает меню настроек с актуальным состоянием."""
    current_time = await get_setting('report_time', DEFAULT_REPORT_TIME)
    subscribed = await is_subscriber(callback.message.chat.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(current_time, subscribed),
        parse_mode="HTML"
    )
    await callback.answer()


async def _send_calc_params(callback: CallbackQuery):
    """Показывает подменю параметров расчёта."""
    days_n = int(await get_setting('calc_days_threshold', str(DEFAULT_DAYS_N)))
    threshold_a = float(await get_setting('calc_threshold_a', str(DEFAULT_THRESHOLD_A)))
    threshold_b = float(await get_setting('calc_threshold_b', str(DEFAULT_THRESHOLD_B)))
    await callback.message.edit_text(
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(days_n, threshold_a, threshold_b),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "settings"))
async def menu_settings(callback: CallbackQuery):
    """Показать меню настроек."""
    await _send_settings(callback)


@router.callback_query(NavCB.filter(F.target == "settings"))
async def nav_settings(callback: CallbackQuery):
    """Возврат в настройки."""
    await _send_settings(callback)


@router.callback_query(SettingsCB.filter(F.action == "calc_params"))
async def menu_calc_params(callback: CallbackQuery):
    """Показать подменю параметров расчёта."""
    await _send_calc_params(callback)


@router.callback_query(NavCB.filter(F.target == "calc_params"))
async def nav_calc_params(callback: CallbackQuery):
    """Возврат к параметрам расчёта."""
    await _send_calc_params(callback)


@router.callback_query(SubscribeCB.filter(F.action == "toggle"))
async def toggle_subscription(callback: CallbackQuery):
    """Подписка/отписка от ежедневных отчётов."""
    chat_id = callback.message.chat.id
    subscribed = await is_subscriber(chat_id)

    if subscribed:
        await remove_subscriber(chat_id)
        await callback.answer("Вы отписались от рассылки", show_alert=True)
        logger.info(f"Пользователь {chat_id} отписался от отчётов")
    else:
        await add_subscriber(chat_id)
        await callback.answer("Вы подписались на ежедневные отчёты!", show_alert=True)
        logger.info(f"Пользователь {chat_id} подписался на отчёты")

    await _send_settings(callback)


@router.callback_query(SettingsCB.filter(F.action == "time"))
async def ask_report_time(callback: CallbackQuery, state: FSMContext):
    """Запрос нового времени отчёта."""
    await callback.message.edit_text(
        "🕐 Введите новое время отправки отчёта в формате <b>ЧЧ:ММ</b>\n"
        "(например: 09:00, 18:30)",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.set_report_time)
    await callback.answer()


@router.message(MenuStates.set_report_time, F.text)
async def set_report_time(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода нового времени."""
    text = message.text.strip()

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    current_time = await get_setting('report_time', DEFAULT_REPORT_TIME)
    subscribed = await is_subscriber(chat_id)

    async def edit_bot_msg(msg_text: str, reply_markup=None):
        if bot_msg_id:
            try:
                await bot.edit_message_text(
                    msg_text, chat_id=chat_id, message_id=bot_msg_id,
                    reply_markup=reply_markup, parse_mode="HTML"
                )
                return
            except Exception:
                pass
        await bot.send_message(chat_id, msg_text, reply_markup=reply_markup, parse_mode="HTML")

    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', text):
        await edit_bot_msg(
            "❌ Неверный формат. Введите время как <b>ЧЧ:ММ</b> (например: 09:00)\n\n"
            "🕐 Введите новое время отправки отчёта в формате <b>ЧЧ:ММ</b>\n"
            "(например: 09:00, 18:30)",
            reply_markup=cancel_kb()
        )
        return

    await set_setting('report_time', text)
    reschedule_daily_reports(text)
    await state.clear()

    await edit_bot_msg(
        f"✅ Время отчёта изменено на <b>{text}</b> МСК\n\n"
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(text, subscribed)
    )
    logger.info(f"Время отчёта изменено на {text}")


# === Параметры расчёта: порог дней ===

def _back_to_calc_params_kb():
    """Кнопка отмены с возвратом в параметры расчёта."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data=NavCB(target="calc_params").pack())
    ]])


@router.callback_query(SettingsCB.filter(F.action == "days_threshold"))
async def ask_days_threshold(callback: CallbackQuery, state: FSMContext):
    """Запрос порога дней для повышения цены."""
    current_n = int(await get_setting('calc_days_threshold', str(DEFAULT_DAYS_N)))
    await callback.message.edit_text(
        "📅 <b>Порог дней для повышения цены</b>\n\n"
        f"Текущее значение: <b>{current_n}</b>\n\n"
        "Введите целое число от 1 до 365.\n"
        "Товары с остатком ≤ N дней получат рекомендацию повышения цены.",
        reply_markup=_back_to_calc_params_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.set_days_threshold)
    await callback.answer()


@router.message(MenuStates.set_days_threshold, F.text)
async def set_days_threshold(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода порога дней."""
    text = message.text.strip()

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    async def edit_bot_msg(msg_text: str, reply_markup=None):
        if bot_msg_id:
            try:
                await bot.edit_message_text(
                    msg_text, chat_id=chat_id, message_id=bot_msg_id,
                    reply_markup=reply_markup, parse_mode="HTML"
                )
                return
            except Exception:
                pass
        await bot.send_message(chat_id, msg_text, reply_markup=reply_markup, parse_mode="HTML")

    try:
        n = int(text)
        if not (1 <= n <= 365):
            raise ValueError
    except ValueError:
        await edit_bot_msg(
            "❌ Неверное значение. Введите целое число от 1 до 365.\n\n"
            "📅 <b>Порог дней для повышения цены</b>\n\n"
            "Введите целое число от 1 до 365.",
            reply_markup=_back_to_calc_params_kb()
        )
        return

    await set_setting('calc_days_threshold', str(n))
    await state.clear()

    threshold_a = float(await get_setting('calc_threshold_a', str(DEFAULT_THRESHOLD_A)))
    threshold_b = float(await get_setting('calc_threshold_b', str(DEFAULT_THRESHOLD_B)))
    await edit_bot_msg(
        f"✅ Порог дней изменён на <b>{n}</b>\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(n, threshold_a, threshold_b)
    )
    logger.info(f"calc_days_threshold изменён на {n}")


# === Параметры расчёта: характеристики групп ===

@router.callback_query(SettingsCB.filter(F.action == "group_thresholds"))
async def ask_group_thresholds(callback: CallbackQuery, state: FSMContext):
    """Запрос характеристик групп A/B."""
    threshold_a = float(await get_setting('calc_threshold_a', str(DEFAULT_THRESHOLD_A)))
    threshold_b = float(await get_setting('calc_threshold_b', str(DEFAULT_THRESHOLD_B)))
    await callback.message.edit_text(
        "📦 <b>Характеристики групп товаров</b>\n\n"
        f"Текущие: A≥{threshold_a} ; B≥{threshold_b}\n\n"
        "Введите два порога через точку с запятой:\n"
        "<code>порог_A ; порог_B</code>\n"
        "Пример: <code>4 ; 0.5</code>\n\n"
        "📌 Что означают параметры:\n"
        "  • <b>порог_A</b> — мин. продаж/день, чтобы товар считался ходовым (группа A).\n"
        "    Для группы A среднее считается по последним 7 дням.\n"
        "  • <b>порог_B</b> — мин. продаж/день для группы B (средние).\n"
        "    Для группы B среднее по 14 дням, ниже порога — группа C (редкие, среднее по 30 дням).\n\n"
        "Чем выше порог_A — тем меньше товаров попадают в «ходовые».",
        reply_markup=_back_to_calc_params_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.set_group_thresholds)
    await callback.answer()


@router.message(MenuStates.set_group_thresholds, F.text)
async def set_group_thresholds(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода порогов групп."""
    text = message.text.strip()

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    async def edit_bot_msg(msg_text: str, reply_markup=None):
        if bot_msg_id:
            try:
                await bot.edit_message_text(
                    msg_text, chat_id=chat_id, message_id=bot_msg_id,
                    reply_markup=reply_markup, parse_mode="HTML"
                )
                return
            except Exception:
                pass
        await bot.send_message(chat_id, msg_text, reply_markup=reply_markup, parse_mode="HTML")

    error_msg = (
        "❌ Неверный формат. Введите два числа через точку с запятой.\n"
        "Пример: <code>4 ; 0.5</code>\n"
        "Обязательно: порог_A > порог_B > 0."
    )

    parts = text.split(';')
    if len(parts) != 2:
        await edit_bot_msg(error_msg, reply_markup=_back_to_calc_params_kb())
        return

    try:
        a = float(parts[0].strip())
        b = float(parts[1].strip())
    except ValueError:
        await edit_bot_msg(error_msg, reply_markup=_back_to_calc_params_kb())
        return

    if not (a > 0 and b > 0 and a > b):
        await edit_bot_msg(
            "❌ Ошибка: оба числа должны быть > 0 и порог_A должен быть больше порог_B.\n\n"
            + error_msg,
            reply_markup=_back_to_calc_params_kb()
        )
        return

    await set_setting('calc_threshold_a', str(a))
    await set_setting('calc_threshold_b', str(b))
    await state.clear()

    days_n = int(await get_setting('calc_days_threshold', str(DEFAULT_DAYS_N)))
    await edit_bot_msg(
        f"✅ Характеристики групп обновлены: A≥{a} · B≥{b}\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(days_n, a, b)
    )
    logger.info(f"calc_threshold_a={a}, calc_threshold_b={b}")
