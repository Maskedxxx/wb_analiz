"""
Настройки: время отчётов, параметры расчёта.
"""

import json
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.keyboards import MenuCB, SettingsCB, NavCB, SubscribeCB, settings_kb, calc_params_kb, cancel_kb
from bot.core.states import MenuStates
from bot.config import (
    REPORT_TIME as DEFAULT_REPORT_TIME,
    DEFAULT_DAYS_N,
    THRESHOLD_A as DEFAULT_THRESHOLD_A,
    THRESHOLD_B as DEFAULT_THRESHOLD_B,
    THRESHOLD_C as DEFAULT_THRESHOLD_C,
    DEFAULT_REFILL_RESERVE_PCT,
    REFILL_PERIOD_DAYS as DEFAULT_REFILL_PERIOD_DAYS,
    MAX_REFILL_WAREHOUSES,
)
from bot.db import get_setting, set_setting, is_subscriber, add_subscriber, remove_subscriber, get_calc_params
from bot.services.scheduler import get_scheduler
from bot.utils.messages import edit_or_send
from bot.db.warehouse import get_unique_warehouses
from bot.services.calculations import parse_distribution_string

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
    params = await get_calc_params()
    await callback.message.edit_text(
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(
            days_n=params.days_threshold,
            threshold_a=params.threshold_a,
            threshold_b=params.threshold_b,
            threshold_c=params.threshold_c,
            refill_reserve_pct=params.refill_reserve_pct,
            refill_period_days=params.refill_period_days,
        ),
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
        await edit_or_send(bot, chat_id, bot_msg_id, msg_text, reply_markup)

    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', text):
        await edit_bot_msg(
            "❌ Неверный формат. Введите время как <b>ЧЧ:ММ</b> (например: 09:00)\n\n"
            "🕐 Введите новое время отправки отчёта в формате <b>ЧЧ:ММ</b>\n"
            "(например: 09:00, 18:30)",
            reply_markup=cancel_kb()
        )
        return

    await set_setting('report_time', text)
    scheduler = get_scheduler()
    if scheduler:
        scheduler.reschedule(text)
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
        await edit_or_send(bot, chat_id, bot_msg_id, msg_text, reply_markup)

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

    params = await get_calc_params()
    await edit_bot_msg(
        f"✅ Порог дней изменён на <b>{n}</b>\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(
            days_n=params.days_threshold,
            threshold_a=params.threshold_a,
            threshold_b=params.threshold_b,
            threshold_c=params.threshold_c,
            refill_reserve_pct=params.refill_reserve_pct,
            refill_period_days=params.refill_period_days,
        )
    )
    logger.info(f"calc_days_threshold изменён на {n}")


# === Параметры расчёта: характеристики групп ===

@router.callback_query(SettingsCB.filter(F.action == "group_thresholds"))
async def ask_group_thresholds(callback: CallbackQuery, state: FSMContext):
    """Запрос характеристик групп A/B/C/D."""
    threshold_a = float(await get_setting('calc_threshold_a', str(DEFAULT_THRESHOLD_A)))
    threshold_b = float(await get_setting('calc_threshold_b', str(DEFAULT_THRESHOLD_B)))
    threshold_c = float(await get_setting('calc_threshold_c', str(DEFAULT_THRESHOLD_C)))
    await callback.message.edit_text(
        "📦 <b>Группы товаров по скорости продаж</b>\n\n"
        f"Текущие пороги (шт/день):\n"
        f"  <b>A</b> ≥ {threshold_a} — ходовые\n"
        f"  <b>B</b> ≥ {threshold_b} — средние\n"
        f"  <b>C</b> ≥ {threshold_c} — редкие\n"
        f"  <b>D</b> <; {threshold_c} — почти не продаются\n\n"
        "Введите три порога через точку с запятой:\n"
        "<code>A ; B ; C</code>\n"
        "Пример: <code>4 ; 0.5 ; 0.2</code>\n\n"
        "Порог C отсекает товары с единичными продажами\n"
        f"(сейчас <;{threshold_c} — реже 1 шт/неделю → группа D).",
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
        await edit_or_send(bot, chat_id, bot_msg_id, msg_text, reply_markup)

    error_msg = (
        "❌ Неверный формат. Введите три числа через точку с запятой:\n"
        "<code>A ; B ; C</code>\n"
        "Пример: <code>4 ; 0.5 ; 0.2</code>\n"
        "Обязательно: A >; B >; C >; 0."
    )

    parts = text.split(';')
    if len(parts) not in (2, 3):
        await edit_bot_msg(error_msg, reply_markup=_back_to_calc_params_kb())
        return

    try:
        a = float(parts[0].strip())
        b = float(parts[1].strip())
        c = float(parts[2].strip()) if len(parts) == 3 else DEFAULT_THRESHOLD_C
    except ValueError:
        await edit_bot_msg(error_msg, reply_markup=_back_to_calc_params_kb())
        return

    if not (a > b > c > 0):
        await edit_bot_msg(
            "❌ Пороги должны быть >; 0 и идти по убыванию: A >; B >; C.\n\n"
            + error_msg,
            reply_markup=_back_to_calc_params_kb()
        )
        return

    await set_setting('calc_threshold_a', str(a))
    await set_setting('calc_threshold_b', str(b))
    await set_setting('calc_threshold_c', str(c))
    await state.clear()

    params = await get_calc_params()
    await edit_bot_msg(
        f"✅ Пороги обновлены: A≥{a} · B≥{b} · C≥{c} · D<{c}\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(
            days_n=params.days_threshold,
            threshold_a=params.threshold_a,
            threshold_b=params.threshold_b,
            threshold_c=params.threshold_c,
            refill_reserve_pct=params.refill_reserve_pct,
            refill_period_days=params.refill_period_days,
        )
    )
    logger.info(f"calc_threshold: A={a}, B={b}, C={c}")



@router.callback_query(SettingsCB.filter(F.action == "refill_reserve"))
async def ask_refill_reserve(callback: CallbackQuery, state: FSMContext):
    """Запрос процента запаса пополнения."""
    current = int(await get_setting('refill_reserve_pct', str(DEFAULT_REFILL_RESERVE_PCT)))
    await callback.message.edit_text(
        "➕ <b>Запас пополнения остатков (%)</b>\n\n"
        f"Текущее значение: <b>{current}%</b>\n\n"
        "Формула: <code>refill = avg × дни × (1 + запас/100)</code>\n\n"
        "Введите целое число от 0 до 200.",
        reply_markup=_back_to_calc_params_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.set_refill_reserve)
    await callback.answer()


@router.message(MenuStates.set_refill_reserve, F.text)
async def set_refill_reserve(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода процента запаса."""
    text = message.text.strip().rstrip('%').strip()

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    async def edit_bot_msg(msg_text: str, reply_markup=None):
        await edit_or_send(bot, chat_id, bot_msg_id, msg_text, reply_markup)

    try:
        pct = int(text)
        if not (0 <= pct <= 200):
            raise ValueError
    except ValueError:
        await edit_bot_msg(
            "❌ Неверное значение. Введите целое число от 0 до 200.\n\n"
            "➕ <b>Запас пополнения остатков (%)</b>",
            reply_markup=_back_to_calc_params_kb()
        )
        return

    await set_setting('refill_reserve_pct', str(pct))
    await state.clear()

    params = await get_calc_params()
    await edit_bot_msg(
        f"✅ Запас пополнения: <b>{pct}%</b>\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(
            days_n=params.days_threshold,
            threshold_a=params.threshold_a,
            threshold_b=params.threshold_b,
            threshold_c=params.threshold_c,
            refill_reserve_pct=params.refill_reserve_pct,
            refill_period_days=params.refill_period_days,
        )
    )
    logger.info(f"refill_reserve_pct: {pct}")


@router.callback_query(SettingsCB.filter(F.action == "refill_period"))
async def ask_refill_period(callback: CallbackQuery, state: FSMContext):
    """Запрос срока расчёта объёма поставки (дни)."""
    current = int(await get_setting('refill_period_days', str(DEFAULT_REFILL_PERIOD_DAYS)))
    await callback.message.edit_text(
        "📆 <b>Срок расчёта объёма поставки</b>\n\n"
        f"Текущее значение: <b>{current} дн</b>\n\n"
        "Формула: <code>Объём = avg_day × n × (1 + буфер/100)</code>\n\n"
        "Введите целое число от 1 до 365.",
        reply_markup=_back_to_calc_params_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.set_refill_period)
    await callback.answer()


@router.message(MenuStates.set_refill_period, F.text)
async def set_refill_period(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода срока расчёта объёма."""
    text = message.text.strip()

    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    async def edit_bot_msg(msg_text: str, reply_markup=None):
        await edit_or_send(bot, chat_id, bot_msg_id, msg_text, reply_markup)

    try:
        n = int(text)
        if not (1 <= n <= 365):
            raise ValueError
    except ValueError:
        await edit_bot_msg(
            "❌ Неверное значение. Введите целое число от 1 до 365.\n\n"
            "📆 <b>Срок расчёта объёма поставки</b>",
            reply_markup=_back_to_calc_params_kb()
        )
        return

    await set_setting('refill_period_days', str(n))
    await state.clear()

    params = await get_calc_params()
    await edit_bot_msg(
        f"✅ Срок расчёта объёма: <b>{n} дн</b>\n\n"
        "📐 <b>Параметры расчёта</b>",
        reply_markup=calc_params_kb(
            days_n=params.days_threshold,
            threshold_a=params.threshold_a,
            threshold_b=params.threshold_b,
            threshold_c=params.threshold_c,
            refill_reserve_pct=params.refill_reserve_pct,
            refill_period_days=params.refill_period_days,
        )
    )
    logger.info(f"refill_period_days: {n}")


# ── Распределение по складам ─────────────────────────────────────────────────


def _warehouse_distrib_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.keyboards import SettingsCB, NavCB
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✏ Изменить (строкой)",
            callback_data=SettingsCB(action="wh_distrib_edit").pack(),
        )],
        [InlineKeyboardButton(
            text="📋 Справочник складов",
            callback_data=SettingsCB(action="wh_distrib_list").pack(),
        )],
        [InlineKeyboardButton(
            text="← Назад",
            callback_data=NavCB(target="settings").pack(),
        )],
    ])


async def _format_distrib_text(distrib: list[dict]) -> str:
    if not distrib:
        return "Распределение не настроено."
    lines = []
    total_w = 0
    for wc in distrib:
        wid = wc.get('warehouse_id', '?')
        name = wc.get('display_name', f'Склад {wid}')
        w = wc.get('weight', 0)
        cut = wc.get('cutoff_days', 0)
        total_w += w
        lines.append(f"  [{wid}] {name} — {w}% / {cut} д")
    lines.append(f"\n  Σ весов: {total_w}%")
    return "\n".join(lines)


@router.callback_query(SettingsCB.filter(F.action == "warehouse_distrib"))
async def show_warehouse_distrib(callback: CallbackQuery):
    """Показывает текущее распределение по складам."""
    raw = await get_setting('refill_warehouse_distribution', '[]')
    try:
        distrib = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        distrib = []
    text = await _format_distrib_text(distrib)
    await callback.message.edit_text(
        f"🏭 <b>Склады поставок</b>\n\n<pre>{text}</pre>",
        reply_markup=_warehouse_distrib_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCB.filter(F.action == "wh_distrib_edit"))
async def wh_distrib_edit_start(callback: CallbackQuery, state: FSMContext):
    """Начинает ввод строки распределения."""
    from bot.keyboards import NavCB
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена",
                              callback_data=SettingsCB(action="warehouse_distrib").pack())],
    ])
    await callback.message.edit_text(
        "✏ <b>Введите строку распределения</b>\n\n"
        f"Формат: <code>id-вес-отсечка, ...</code> (макс {MAX_REFILL_WAREHOUSES})\n"
        "Пример: <code>507-25-3, 117501-20-3, 686-15-2</code>\n\n"
        "id — ID склада WB (из справочника)\n"
        "вес — % от общего объёма\n"
        "отсечка — дни на пополнение склада",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await state.set_state(MenuStates.refill_distrib_enter)
    await state.update_data(bot_msg_id=callback.message.message_id)
    await callback.answer()


@router.message(MenuStates.refill_distrib_enter)
async def wh_distrib_enter_string(message: Message, state: FSMContext, bot: Bot):
    """Парсит строку и показывает расшифровку."""
    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')

    async def edit_bot_msg(text, reply_markup=None):
        try:
            await bot.edit_message_text(
                text, chat_id=message.chat.id, message_id=bot_msg_id,
                reply_markup=reply_markup, parse_mode="HTML",
            )
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    raw = message.text or ''
    try:
        parsed = parse_distribution_string(raw)
    except ValueError as e:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена",
                                  callback_data=SettingsCB(action="warehouse_distrib").pack())],
        ])
        await edit_bot_msg(f"❌ {e}\n\nПопробуйте ещё раз:", reply_markup=kb)
        return

    # Лукап имён
    known = {w['id']: w for w in await get_unique_warehouses()}
    distrib = []
    lines = []
    total_w = 0
    for p in parsed:
        wid = p['warehouse_id']
        info = known.get(wid)
        name = info['name'] if info else f'Неизвестный [{wid}]'
        region = info.get('region', '') if info else ''
        mark = '✅' if info else '⚠'
        lines.append(f"  {mark} [{wid}] {name} — {p['weight']}% / {p['cutoff_days']} д")
        total_w += p['weight']
        distrib.append({
            'warehouse_id': wid,
            'display_name': name,
            'region': region,
            'weight': p['weight'],
            'cutoff_days': p['cutoff_days'],
        })
    lines.append(f"\n  Σ весов: {total_w}%")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить",
                              callback_data=SettingsCB(action="wh_distrib_save").pack())],
        [InlineKeyboardButton(text="❌ Отмена",
                              callback_data=SettingsCB(action="warehouse_distrib").pack())],
    ])
    await state.update_data(pending_distrib=json.dumps(distrib, ensure_ascii=False))
    await state.set_state(MenuStates.refill_distrib_confirm)
    text = "\n".join(lines)
    await edit_bot_msg(
        f"🏭 <b>Распарсил {len(parsed)} складов:</b>\n<pre>{text}</pre>\n\n"
        "Подтвердите сохранение:",
        reply_markup=kb,
    )


@router.callback_query(SettingsCB.filter(F.action == "wh_distrib_save"))
async def wh_distrib_save(callback: CallbackQuery, state: FSMContext):
    """Сохраняет распределение."""
    data = await state.get_data()
    pending = data.get('pending_distrib', '[]')
    await set_setting('refill_warehouse_distribution', pending)
    await state.clear()

    distrib = json.loads(pending)
    text = await _format_distrib_text(distrib)
    await callback.message.edit_text(
        f"✅ Сохранено!\n\n🏭 <b>Склады поставок</b>\n<pre>{text}</pre>",
        reply_markup=_warehouse_distrib_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
    logger.info(f"warehouse_distribution saved: {len(distrib)} warehouses")


@router.callback_query(SettingsCB.filter(F.action == "wh_distrib_list"))
async def wh_distrib_list(callback: CallbackQuery):
    """Показывает справочник складов."""
    warehouses = await get_unique_warehouses()
    if not warehouses:
        await callback.answer("Нет данных по складам. Сначала сгенерируйте отчёт.", show_alert=True)
        return

    # Группировка по регионам
    by_region = {}
    for w in warehouses:
        region = w.get('region') or 'Без региона'
        name = w.get('name', '?')
        # Фильтруем СЦ по умолчанию
        if any(sc in name.upper() for sc in ('СЦ ', 'СЦ_', ' СЦ', 'СОРТИРОВОЧ')):
            continue
        by_region.setdefault(region, []).append(w)

    lines = ["📋 Доступные склады:\n"]
    for region in sorted(by_region.keys()):
        lines.append(f"🏛 {region}:")
        for w in sorted(by_region[region], key=lambda x: x.get('name', '')):
            lines.append(f"  [{w['id']}] {w['name']}")
        lines.append("")
    lines.append("(СЦ скрыты)")

    text = "\n".join(lines)
    # Telegram limit: 4096 chars
    if len(text) > 4000:
        text = text[:4000] + "\n... (список обрезан)"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад",
                              callback_data=SettingsCB(action="warehouse_distrib").pack())],
    ])
    await callback.message.edit_text(
        f"<pre>{text}</pre>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()
