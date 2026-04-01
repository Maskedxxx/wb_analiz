"""
Сравнение магазинов: подменю режимов, сравнение пары, сводный отчёт.
"""

import os
import asyncio
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    MenuCB, CompareCB, CompareModeCB, NavCB,
    comparison_mode_kb, compare_stores_kb, store_display_name, back_to_menu_kb,
)
from bot.core.states import MenuStates
from bot.db import (
    get_stores, get_store, get_setting,
    save_report_history, log_action,
)
from bot.services.data_service import fetch_or_cache_product, fetch_or_cache_warehouse
from bot.reports.comparison import generate_comparison_report
from bot.reports.summary import generate_summary_report
from bot.services.wb_client import WBTokenError

logger = logging.getLogger(__name__)

router = Router()


# ── Подменю сравнения ────────────────────────────────────────────────────────

@router.callback_query(MenuCB.filter(F.action == "comparison"))
async def start_comparison(callback: CallbackQuery, state: FSMContext):
    """Показать подменю: Сравнение пары / Сводный отчёт."""
    stores = await get_stores()
    if len(stores) < 2:
        await callback.answer(
            "Для сравнения нужно минимум 2 магазина. Добавьте в настройках.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🔀 <b>Сравнение магазинов</b>\n\n"
        "Выберите режим:",
        reply_markup=comparison_mode_kb(),
        parse_mode="HTML",
    )
    await state.set_state(MenuStates.comparison_mode)
    await callback.answer()


# ── Сравнение пары ───────────────────────────────────────────────────────────

@router.callback_query(
    CompareModeCB.filter(F.action == "pair"),
    MenuStates.comparison_mode,
)
async def start_pair_comparison(callback: CallbackQuery, state: FSMContext):
    """Режим сравнения пары: показать список магазинов для первого выбора."""
    stores = await get_stores()

    await callback.message.edit_text(
        "🔀 <b>Сравнение пары</b>\n\n"
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
        f"🔀 <b>Сравнение пары</b>\n\n"
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
        threshold_c = float(await get_setting('calc_threshold_c', '0.2'))

        data1, data2 = await asyncio.wait_for(
            asyncio.gather(
                fetch_or_cache_product(store1_id, store1['token'], days_threshold, threshold_a, threshold_b),
                fetch_or_cache_product(store2_id, store2['token'], days_threshold, threshold_a, threshold_b),
            ),
            timeout=300,
        )

        await progress_msg.edit_text(
            f"⏳ <b>{name1}</b> vs <b>{name2}</b>\n\n"
            "2/3 · Данные загружены. Формирование Excel...",
            parse_mode="HTML",
        )

        report_path = await asyncio.to_thread(
            generate_comparison_report,
            store1_data=data1, store2_data=data2,
            store1_name=name1, store2_name=name2,
            days_threshold=days_threshold,
            threshold_a=threshold_a, threshold_b=threshold_b,
            threshold_c=threshold_c,
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

    except asyncio.TimeoutError:
        await progress_msg.edit_text(
            f"⏱ <b>Таймаут</b>\n\n"
            "WB API не ответил за 5 минут. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
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


# ── Сводный отчёт ────────────────────────────────────────────────────────────

@router.callback_query(
    CompareModeCB.filter(F.action == "summary"),
    MenuStates.comparison_mode,
)
async def start_summary_report(callback: CallbackQuery, state: FSMContext):
    """Сводный отчёт по всем магазинам."""
    stores = await get_stores()
    if len(stores) < 2:
        await callback.answer(
            "Для сводного отчёта нужно минимум 2 магазина.",
            show_alert=True,
        )
        return

    store_names = [store_display_name(s) for s in stores]
    progress_msg = callback.message
    await progress_msg.edit_text(
        "📋 <b>Сводный отчёт</b>\n\n"
        f"Магазинов: {len(stores)}\n"
        "1/3 · Загрузка данных из WB API...",
        parse_mode="HTML",
    )
    await callback.answer()
    await state.clear()

    try:
        days_threshold = int(await get_setting('calc_days_threshold', '7'))
        threshold_a = float(await get_setting('calc_threshold_a', '4.0'))
        threshold_b = float(await get_setting('calc_threshold_b', '0.5'))
        threshold_c = float(await get_setting('calc_threshold_c', '0.2'))

        # Параллельная загрузка данных всех магазинов
        product_tasks = []
        warehouse_tasks = []
        for s in stores:
            product_tasks.append(
                fetch_or_cache_product(s['id'], s['token'], days_threshold, threshold_a, threshold_b)
            )
            warehouse_tasks.append(
                fetch_or_cache_warehouse(s['id'], s['token'])
            )

        all_product_results = await asyncio.wait_for(
            asyncio.gather(*product_tasks), timeout=300,
        )
        all_warehouse_results = await asyncio.wait_for(
            asyncio.gather(*warehouse_tasks), timeout=300,
        )

        # Собираем dict {store_name: data}
        all_stores_data = {}
        all_warehouse_data = {}
        for i, s in enumerate(stores):
            name = store_display_name(s)
            all_stores_data[name] = all_product_results[i]
            all_warehouse_data[name] = all_warehouse_results[i]

        await progress_msg.edit_text(
            "📋 <b>Сводный отчёт</b>\n\n"
            "2/3 · Данные загружены. Формирование Excel...",
            parse_mode="HTML",
        )

        report_path = await asyncio.to_thread(
            generate_summary_report,
            all_stores_data=all_stores_data,
            all_warehouse_data=all_warehouse_data,
            days_threshold=days_threshold,
            threshold_a=threshold_a,
            threshold_b=threshold_b,
            threshold_c=threshold_c,
        )

        if report_path is None:
            await progress_msg.edit_text(
                "📋 <b>Сводный отчёт</b>\n\n"
                "Нет артикулов, присутствующих в 2+ магазинах.",
                reply_markup=back_to_menu_kb(),
                parse_mode="HTML",
            )
            return

        try:
            await progress_msg.delete()
        except Exception:
            pass
        document = FSInputFile(report_path, filename=os.path.basename(report_path))
        await callback.message.answer_document(
            document,
            caption=f"✅ Сводный отчёт ({len(stores)} магазинов)",
            reply_markup=back_to_menu_kb(),
        )
        await log_action(callback.from_user.id, 'summary_report', f'{len(stores)} магазинов')

    except asyncio.TimeoutError:
        await progress_msg.edit_text(
            f"⏱ <b>Таймаут</b>\n\n"
            "WB API не ответил за 5 минут. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except WBTokenError as e:
        await progress_msg.edit_text(
            f"🔑 <b>Ошибка токена</b>\n\n{e}\n\n"
            "Обновите токен: ⚙️ Настройки → Управление магазинами",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка сводного отчёта: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ Ошибка сводного отчёта:\n{e}",
            reply_markup=back_to_menu_kb(),
        )
