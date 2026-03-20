"""
Анализ остатков: выбор магазина, генерация/просмотр отчётов.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile

_MSK = timezone(timedelta(hours=3))

from bot.keyboards import (
    MenuCB, StoreCB, NavCB,
    stores_list_kb, store_actions_kb, store_display_name,
)
from bot.config import DATA_CACHE_TTL
from bot.db import (
    get_stores, get_store, get_last_report, save_report_history, get_setting,
    save_product_data, get_latest_product_data, is_data_fresh, log_action,
)
from bot.report import fetch_store_data, generate_report_from_data
from wb_api import WBTokenError

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(MenuCB.filter(F.action == "analysis"))
async def menu_analysis(callback: CallbackQuery):
    """Показывает список магазинов для анализа."""
    stores = await get_stores()
    await callback.message.edit_text(
        "📊 <b>Анализ остатков</b>\n\nВыберите магазин:",
        reply_markup=stores_list_kb(stores, action="select"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(NavCB.filter(F.target == "analysis"))
async def nav_analysis(callback: CallbackQuery):
    """Возврат к списку магазинов."""
    stores = await get_stores()
    await callback.message.edit_text(
        "📊 <b>Анализ остатков</b>\n\nВыберите магазин:",
        reply_markup=stores_list_kb(stores, action="select"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(StoreCB.filter(F.action == "select"))
async def store_selected(callback: CallbackQuery, callback_data: StoreCB):
    """Магазин выбран — показать действия."""
    store = await get_store(callback_data.store_id)
    if not store:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    last_report = await get_last_report(callback_data.store_id)
    last_time = None
    if last_report:
        try:
            raw = last_report['created_at'][:16].replace('T', ' ')
            utc_dt = datetime.strptime(raw, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
            last_time = utc_dt.astimezone(_MSK).strftime('%d.%m %H:%M')
        except Exception:
            last_time = last_report['created_at'][:16]

    name = store_display_name(store)
    await callback.message.edit_text(
        f"🏪 <b>{name}</b>\n\nВыберите действие:",
        reply_markup=store_actions_kb(callback_data.store_id, last_time),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(StoreCB.filter(F.action == "last"))
async def send_last_report(callback: CallbackQuery, callback_data: StoreCB):
    """Отправить последний сохранённый отчёт."""
    last_report = await get_last_report(callback_data.store_id)
    if not last_report or not os.path.exists(last_report['file_path']):
        await callback.answer("Отчёт не найден. Сгенерируйте новый.", show_alert=True)
        return

    document = FSInputFile(
        last_report['file_path'],
        filename=os.path.basename(last_report['file_path'])
    )
    await callback.message.answer_document(
        document,
        caption=f"📄 Отчёт от {last_report['created_at'][:16]}"
    )
    await callback.answer()


@router.callback_query(StoreCB.filter(F.action == "new"))
async def generate_new_report(callback: CallbackQuery, callback_data: StoreCB):
    """Генерация нового отчёта для магазина."""
    store = await get_store(callback_data.store_id)
    if not store:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    name = store_display_name(store)
    await callback.message.edit_text(
        f"⏳ Генерирую отчёт для <b>{name}</b>...\n"
        "Загрузка данных из WB API.",
        parse_mode="HTML"
    )
    await callback.answer()

    try:
        days_threshold = int(await get_setting('calc_days_threshold', '7'))
        threshold_a = float(await get_setting('calc_threshold_a', '4.0'))
        threshold_b = float(await get_setting('calc_threshold_b', '0.5'))

        # 1. Загрузка данных из API (или из кэша если свежие)
        store_id = callback_data.store_id
        if await is_data_fresh(store_id, DATA_CACHE_TTL):
            logger.info(f"Данные для {name} свежие (кэш), пропускаем API")
            product_rows, _ = await get_latest_product_data(store_id)
        else:
            product_rows = await asyncio.to_thread(
                fetch_store_data, token=store['token'],
                days_threshold=days_threshold, threshold_a=threshold_a, threshold_b=threshold_b,
            )
            await save_product_data(store_id, product_rows)

        # 2. Генерация Excel из данных
        report_path = await asyncio.to_thread(
            generate_report_from_data, product_rows=product_rows, store_name=name,
            days_threshold=days_threshold, threshold_a=threshold_a, threshold_b=threshold_b,
        )
        await save_report_history(store_id, report_path)

        document = FSInputFile(report_path, filename=os.path.basename(report_path))
        await callback.message.answer_document(document, caption=f"📊 Отчёт для {name} готов!")
        await log_action(callback.from_user.id, 'report_gen', f'store={name}')

    except WBTokenError as e:
        await callback.message.edit_text(
            f"🔑 <b>Ошибка токена для {name}</b>\n\n"
            f"{e}\n\n"
            "Обновите токен: ⚙️ Настройки → Управление магазинами",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации отчёта для {name}: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка генерации отчёта для {name}:\n{e}"
        )
