"""
Главное меню: /start, /menu, навигация.
"""

import logging
from datetime import datetime, timezone

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.config import BOT_PASSWORD, MSK_TZ
from bot.keyboards import MenuCB, NavCB, main_menu_kb, store_display_name
from bot.db import get_stores, get_last_reports_batch, get_setting, is_subscriber, is_authorized, authorize_user, log_action
from bot.core.security import verify_password
from bot.core.states import MenuStates

logger = logging.getLogger(__name__)

router = Router()

DEFAULT_REPORT_TIME = "09:00"


async def _send_main_menu(target, stores: list = None):
    """Отправляет или редактирует главное меню с информацией."""
    if stores is None:
        stores = await get_stores()

    if isinstance(target, Message):
        chat_id = target.chat.id
    else:
        chat_id = target.message.chat.id

    subscribed = await is_subscriber(chat_id)
    report_time = await get_setting('report_time', DEFAULT_REPORT_TIME)

    text = "📊 <b>WB Analiz Bot</b>\n\n"

    # Магазины с датой последнего отчёта
    text += f"🏪 Магазинов: {len(stores)}\n"
    if stores:
        last_reports = await get_last_reports_batch([s['id'] for s in stores])
        for s in stores:
            name = store_display_name(s)
            last = last_reports.get(s['id'])
            if last:
                # created_at хранится в UTC (SQLite datetime('now')), конвертируем в МСК
                try:
                    raw = last['created_at'][:16].replace('T', ' ')
                    utc_dt = datetime.strptime(raw, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                    msk_dt = utc_dt.astimezone(MSK_TZ)
                    dt_short = msk_dt.strftime('%d.%m %H:%M')
                except Exception:
                    dt_short = last['created_at'][:16]
                text += f"  • {name} — {dt_short}\n"
            else:
                text += f"  • {name} — нет отчётов\n"
    else:
        text += "  ⚠️ Нет подключённых магазинов\n"

    # Статус рассылки
    sub_icon = "🔔" if subscribed else "🔕"
    sub_label = "активна" if subscribed else "отключена"
    text += f"\n⏰ Рассылка: {report_time} МСК · {sub_icon} {sub_label}\n"
    text += "\nВыберите действие:"

    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
        except TelegramBadRequest:
            # Сообщение-документ нельзя edit_text — отправляем новое
            await target.message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
        await target.answer()


@router.message(Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик /start — показывает главное меню или запрашивает пароль."""
    if not BOT_PASSWORD or await is_authorized(message.from_user.id):
        await state.clear()
        await _send_main_menu(message)
    else:
        await message.answer("🔑 Введите пароль для доступа к боту:")
        await state.set_state(MenuStates.waiting_password)


@router.message(MenuStates.waiting_password, F.text)
async def process_password(message: Message, state: FSMContext, bot: Bot):
    """Проверка пароля при авторизации."""
    password = message.text.strip()

    # Удаляем сообщение с паролем из чата
    try:
        await message.delete()
    except Exception:
        pass

    if verify_password(password, BOT_PASSWORD):
        await authorize_user(message.from_user.id)
        await log_action(message.from_user.id, 'auth_ok', f'@{message.from_user.username}')
        logger.info(
            f"User {message.from_user.id} (@{message.from_user.username}) authorized successfully"
        )
        await state.clear()
        await bot.send_message(
            message.chat.id,
            "✅ Авторизация успешна!\n"
        )
        await _send_main_menu(message)
    else:
        await log_action(message.from_user.id, 'auth_fail', f'@{message.from_user.username}')
        logger.warning(
            f"Failed auth attempt from user {message.from_user.id} (@{message.from_user.username})"
        )
        await bot.send_message(
            message.chat.id,
            "❌ Неверный пароль. Попробуйте ещё раз:"
        )


@router.message(Command('menu'))
async def cmd_menu(message: Message):
    """Обработчик /menu — показывает главное меню."""
    await _send_main_menu(message)


@router.callback_query(NavCB.filter(F.target == "main"))
async def nav_main(callback: CallbackQuery):
    """Возврат в главное меню."""
    await _send_main_menu(callback)
