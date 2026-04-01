"""
Анализ остатков: выбор магазина, генерация/просмотр отчётов.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile

from bot.keyboards import (
    MenuCB, StoreCB, NavCB,
    stores_list_kb, store_actions_kb, store_display_name, back_to_menu_kb,
)
from bot.config import MSK_TZ
from bot.db import (
    get_stores, get_store, get_last_report, save_report_history, get_setting,
    log_action,
)
from bot.services.data_service import fetch_or_cache_product, fetch_or_cache_warehouse
from bot.reports.single import generate_report_from_data
from bot.services.wb_client import WBTokenError

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
            last_time = utc_dt.astimezone(MSK_TZ).strftime('%d.%m %H:%M')
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
        caption=f"📄 Отчёт от {last_report['created_at'][:16]}",
        reply_markup=back_to_menu_kb(),
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

    progress_msg = callback.message

    try:
        days_threshold = int(await get_setting('calc_days_threshold', '7'))
        threshold_a = float(await get_setting('calc_threshold_a', '4.0'))
        threshold_b = float(await get_setting('calc_threshold_b', '0.5'))
        threshold_c = float(await get_setting('calc_threshold_c', '0.2'))

        # 1. Загрузка данных из API (или из кэша если свежие)
        store_id = callback_data.store_id
        product_rows = await fetch_or_cache_product(
            store_id, store['token'], days_threshold, threshold_a, threshold_b,
        )

        # 2. Загрузка данных по складам (для детализации остатков)
        warehouse_rows = await fetch_or_cache_warehouse(store_id, store['token'])

        # 3. Генерация Excel из данных
        await progress_msg.edit_text(
            f"⏳ Генерирую отчёт для <b>{name}</b>...\n"
            "Формирование Excel.",
            parse_mode="HTML"
        )
        report_path = await asyncio.to_thread(
            generate_report_from_data, product_rows=product_rows, store_name=name,
            days_threshold=days_threshold, threshold_a=threshold_a, threshold_b=threshold_b,
            threshold_c=threshold_c, warehouse_rows=warehouse_rows,
        )
        await save_report_history(store_id, report_path)

        # Удаляем прогресс-сообщение, отправляем файл с кнопкой
        try:
            await progress_msg.delete()
        except Exception:
            pass
        document = FSInputFile(report_path, filename=os.path.basename(report_path))
        await callback.message.answer_document(
            document,
            caption=f"📊 Отчёт для {name}",
            reply_markup=back_to_menu_kb(),
        )
        await log_action(callback.from_user.id, 'report_gen', f'store={name}')

    except WBTokenError as e:
        await progress_msg.edit_text(
            f"🔑 <b>Ошибка токена для {name}</b>\n\n"
            f"{e}\n\n"
            "Обновите токен: ⚙️ Настройки → Управление магазинами",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации отчёта для {name}: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ Ошибка генерации отчёта для {name}:\n{e}",
            reply_markup=back_to_menu_kb(),
        )
