"""
Управление магазинами: добавление, редактирование, удаление.
"""

import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    SettingsCB, StoreCB, NavCB,
    store_management_kb, confirm_delete_kb, cancel_kb, store_display_name,
)
from bot.states import MenuStates
from bot.db import get_stores, get_store, add_store, update_store, delete_store, log_action
from wb_api import get_seller_info, WBTokenError

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(SettingsCB.filter(F.action == "stores"))
async def manage_stores(callback: CallbackQuery):
    """Показать список магазинов для управления."""
    stores = await get_stores()
    await callback.message.edit_text(
        "🏪 <b>Управление магазинами</b>",
        reply_markup=store_management_kb(stores),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(NavCB.filter(F.target == "store_mgmt"))
async def nav_store_mgmt(callback: CallbackQuery, state: FSMContext):
    """Возврат к управлению магазинами."""
    await state.clear()
    stores = await get_stores()
    await callback.message.edit_text(
        "🏪 <b>Управление магазинами</b>",
        reply_markup=store_management_kb(stores),
        parse_mode="HTML"
    )
    await callback.answer()


# === Добавление магазина ===

@router.callback_query(StoreCB.filter(F.action == "add"))
async def ask_store_token(callback: CallbackQuery, state: FSMContext):
    """Запрос токена нового магазина."""
    await callback.message.edit_text(
        "🔑 Отправьте <b>токен WB API</b> нового магазина.\n\n"
        "Токен можно получить в личном кабинете WB → Настройки → Доступ к API",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.add_store_token)
    await callback.answer()


@router.message(MenuStates.add_store_token, F.text)
async def process_store_token(message: Message, state: FSMContext, bot: Bot):
    """Проверка токена и добавление магазина."""
    token = message.text.strip()

    # Удалить сообщение пользователя с токеном (чувствительные данные)
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    async def edit_bot_msg(text: str, reply_markup=None):
        if bot_msg_id:
            try:
                await bot.edit_message_text(
                    text, chat_id=chat_id, message_id=bot_msg_id,
                    reply_markup=reply_markup, parse_mode="HTML"
                )
                return
            except Exception:
                pass
        await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")

    if len(token) < 10:
        await edit_bot_msg(
            "❌ Токен слишком короткий. Проверьте правильность.",
            reply_markup=cancel_kb()
        )
        return

    await edit_bot_msg("⏳ Проверяю токен...")

    try:
        info = await asyncio.to_thread(get_seller_info, token)
        name = info.get('name', 'Новый магазин') if info else 'Новый магазин'
        trade_mark = info.get('tradeMark') if info else None
    except WBTokenError:
        await edit_bot_msg(
            "❌ Токен невалиден или истёк.\n"
            "Проверьте правильность токена и попробуйте снова.",
            reply_markup=cancel_kb()
        )
        return
    except Exception as e:
        logger.warning(f"Не удалось получить имя магазина: {e}")
        name = 'Новый магазин'
        trade_mark = None

    store_id = await add_store(token, name)
    if trade_mark:
        await update_store(store_id, marketplace_name=trade_mark)
    await state.clear()

    stores = await get_stores()
    await edit_bot_msg(
        f"✅ Магазин <b>{name}</b> добавлен (ID: {store_id})\n\n"
        "🏪 <b>Управление магазинами</b>",
        reply_markup=store_management_kb(stores)
    )
    await log_action(message.from_user.id, 'store_add', f'{name} (ID: {store_id})')
    logger.info(f"Добавлен магазин: {name} (ID: {store_id})")


# === Редактирование торгового названия магазина ===

@router.callback_query(StoreCB.filter(F.action == "edit"))
async def ask_edit_store(callback: CallbackQuery, callback_data: StoreCB, state: FSMContext):
    """Запрос торгового названия магазина (marketplace_name)."""
    store = await get_store(callback_data.store_id)
    if not store:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    current = store.get('marketplace_name') or '—'
    legal = store.get('name') or f"Магазин #{store['id']}"
    await state.update_data(edit_store_id=callback_data.store_id, bot_msg_id=callback.message.message_id)
    await state.set_state(MenuStates.edit_store_name)

    await callback.message.edit_text(
        f"✏️ <b>{legal}</b>\n\n"
        f"Текущее торговое название: <b>{current}</b>\n\n"
        "Введите торговое название (бренд на маркетплейсе).\n"
        "Отправьте <code>-</code> чтобы сбросить.",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(MenuStates.edit_store_name, F.text)
async def process_edit_store(message: Message, state: FSMContext, bot: Bot):
    """Сохранение торгового названия магазина."""
    # Удалить сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    store_id = data.get('edit_store_id')
    bot_msg_id = data.get('bot_msg_id')
    chat_id = message.chat.id

    if not store_id:
        await state.clear()
        return

    new_name = message.text.strip()
    # Сброс торгового названия
    marketplace_name = None if new_name in ('-', '') else new_name
    await update_store(store_id, marketplace_name=marketplace_name)
    await state.clear()

    store = await get_store(store_id)
    display = store_display_name(store) if store else f"Магазин #{store_id}"

    stores = await get_stores()
    result_text = (
        f"✅ Торговое название обновлено: <b>{display}</b>\n\n"
        "🏪 <b>Управление магазинами</b>"
    )

    if bot_msg_id:
        try:
            await bot.edit_message_text(
                result_text, chat_id=chat_id, message_id=bot_msg_id,
                reply_markup=store_management_kb(stores), parse_mode="HTML"
            )
        except Exception:
            await bot.send_message(
                chat_id, result_text,
                reply_markup=store_management_kb(stores), parse_mode="HTML"
            )
    else:
        await bot.send_message(
            chat_id, result_text,
            reply_markup=store_management_kb(stores), parse_mode="HTML"
        )

    logger.info(f"Магазин #{store_id} marketplace_name → {marketplace_name!r}")


# === Удаление магазина ===

@router.callback_query(StoreCB.filter(F.action == "delete"))
async def ask_delete_store(callback: CallbackQuery, callback_data: StoreCB):
    """Подтверждение удаления магазина."""
    store = await get_store(callback_data.store_id)
    if not store:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    name = store_display_name(store)
    await callback.message.edit_text(
        f"❓ Удалить магазин <b>{name}</b>?",
        reply_markup=confirm_delete_kb(callback_data.store_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(StoreCB.filter(F.action == "confirm_delete"))
async def confirm_delete_store(callback: CallbackQuery, callback_data: StoreCB):
    """Удаление магазина после подтверждения."""
    store = await get_store(callback_data.store_id)
    name = store_display_name(store) if store else '?'

    await delete_store(callback_data.store_id)

    stores = await get_stores()
    await callback.message.edit_text(
        f"🗑 Магазин <b>{name}</b> удалён.\n\n"
        "🏪 <b>Управление магазинами</b>",
        reply_markup=store_management_kb(stores),
        parse_mode="HTML"
    )
    await callback.answer()
    await log_action(callback.from_user.id, 'store_delete', f'{name} (ID: {callback_data.store_id})')
    logger.info(f"Магазин #{callback_data.store_id} ({name}) удалён")
