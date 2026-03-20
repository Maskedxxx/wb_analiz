"""
Сравнение магазинов: выбор двух магазинов, генерация сравнительного отчёта.
"""

import os
import asyncio
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    MenuCB, CompareCB, NavCB,
    compare_stores_kb, store_display_name, back_to_menu_kb,
)
from bot.states import MenuStates
from bot.config import DATA_CACHE_TTL
from bot.db import (
    get_stores, get_store, get_setting,
    save_product_data, get_latest_product_data, is_data_fresh,
    save_report_history, log_action,
)
from bot.report import fetch_store_data, generate_comparison_report
from wb_api import WBTokenError

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(MenuCB.filter(F.action == "comparison"))
async def start_comparison(callback: CallbackQuery, state: FSMContext):
    """Начало сравнения: показать список магазинов для первого выбора."""
    stores = await get_stores()
    if len(stores) < 2:
        await callback.answer(
            "Для сравнения нужно минимум 2 магазина. Добавьте в настройках.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🔀 <b>Сравнение магазинов</b>\n\n"
        "Выберите <b>первый</b> магазин:",
        reply_markup=compare_stores_kb(stores, action="select_first"),
        parse_mode="HTML",
    )
    await state.set_state(MenuStates.compare_select_first)
    await callback.answer()


@router.callback_query(
    CompareCB.filter(F.action == "select_first"),
    MenuStates.compare_select_first,
)
async def select_first(callback: CallbackQuery, callback_data: CompareCB, state: FSMContext):
    """Первый магазин выбран — показать список для второго."""
    store = await get_store(callback_data.store_id)
    if not store:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    await state.update_data(compare_store_1=callback_data.store_id)

    stores = await get_stores()
    name = store_display_name(store)
    await callback.message.edit_text(
        f"🔀 <b>Сравнение магазинов</b>\n\n"
        f"Первый: <b>{name}</b>\n"
        f"Выберите <b>второй</b> магазин:",
        reply_markup=compare_stores_kb(stores, action="select_second", exclude_id=callback_data.store_id),
        parse_mode="HTML",
    )
    await state.set_state(MenuStates.compare_select_second)
    await callback.answer()


@router.callback_query(
    CompareCB.filter(F.action == "select_second"),
    MenuStates.compare_select_second,
)
async def select_second(callback: CallbackQuery, callback_data: CompareCB, state: FSMContext):
    """Второй магазин выбран — генерация сравнительного отчёта."""
    data = await state.get_data()
    store1_id = data.get('compare_store_1')
    store2_id = callback_data.store_id

    store1 = await get_store(store1_id)
    store2 = await get_store(store2_id)
    if not store1 or not store2:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    name1 = store_display_name(store1)
    name2 = store_display_name(store2)

    progress_msg = callback.message
    await progress_msg.edit_text(
        f"⏳ <b>{name1}</b> vs <b>{name2}</b>\n\n"
        "1/3 · Загрузка данных из WB API...",
        parse_mode="HTML",
    )
    await callback.answer()
    await state.clear()

    try:
        days_threshold = int(await get_setting('calc_days_threshold', '7'))
        threshold_a = float(await get_setting('calc_threshold_a', '4.0'))
        threshold_b = float(await get_setting('calc_threshold_b', '0.5'))

        # Загрузка данных обоих магазинов
        async def fetch_or_cache(store_id, token, store_name, step_label):
            if await is_data_fresh(store_id, DATA_CACHE_TTL):
                rows, _ = await get_latest_product_data(store_id)
                return rows
            rows = await asyncio.to_thread(
                fetch_store_data, token=token,
                days_threshold=days_threshold,
                threshold_a=threshold_a,
                threshold_b=threshold_b,
            )
            await save_product_data(store_id, rows)
            return rows

        # Параллельная загрузка если оба не в кэше
        data1, data2 = await asyncio.gather(
            fetch_or_cache(store1_id, store1['token'], name1, "1"),
            fetch_or_cache(store2_id, store2['token'], name2, "2"),
        )

        await progress_msg.edit_text(
            f"⏳ <b>{name1}</b> vs <b>{name2}</b>\n\n"
            "2/3 · Данные загружены. Формирование Excel...",
            parse_mode="HTML",
        )

        # Генерация сравнительного отчёта
        report_path = await asyncio.to_thread(
            generate_comparison_report,
            store1_data=data1, store2_data=data2,
            store1_name=name1, store2_name=name2,
            days_threshold=days_threshold,
            threshold_a=threshold_a, threshold_b=threshold_b,
        )

        if report_path is None:
            await progress_msg.edit_text(
                f"🔀 <b>{name1}</b> vs <b>{name2}</b>\n\n"
                "Нет совпадающих артикулов между магазинами.",
                reply_markup=back_to_menu_kb(),
                parse_mode="HTML",
            )
            return

        await save_report_history(store1_id, report_path)

        # Удаляем прогресс-сообщение, отправляем файл с кнопкой
        try:
            await progress_msg.delete()
        except Exception:
            pass
        document = FSInputFile(report_path, filename=os.path.basename(report_path))
        await callback.message.answer_document(
            document,
            caption=f"✅ Сравнение: {name1} vs {name2}",
            reply_markup=back_to_menu_kb(),
        )
        await log_action(callback.from_user.id, 'comparison', f'{name1} vs {name2}')

    except WBTokenError as e:
        await progress_msg.edit_text(
            f"🔑 <b>Ошибка токена</b>\n\n{e}\n\n"
            "Обновите токен: ⚙️ Настройки → Управление магазинами",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка сравнения {name1} vs {name2}: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ Ошибка сравнения:\n{e}",
            reply_markup=back_to_menu_kb(),
        )
