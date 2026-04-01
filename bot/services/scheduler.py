"""
Планировщик ежедневных отчётов для всех магазинов.
"""

import asyncio
import os
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.config import TIMEZONE, MSK_TZ
from bot.db import get_stores, get_setting, save_report_history, get_subscribers
from bot.keyboards import store_display_name
from bot.services.data_service import fetch_or_cache_product, fetch_or_cache_warehouse
from bot.reports.single import generate_report_from_data
from bot.reports.summary import generate_summary_report
from bot.services.wb_client import WBTokenError

logger = logging.getLogger(__name__)

DEFAULT_REPORT_TIME = "09:00"
HEALTH_FILE = os.getenv('HEALTH_FILE', '/tmp/health')

_scheduler: "AsyncIOScheduler | None" = None
_bot: "Bot | None" = None


async def _touch_health():
    """Обновляет mtime файла-маркера для Docker healthcheck."""
    try:
        Path(HEALTH_FILE).touch()
    except Exception:
        pass


async def send_daily_reports(bot: Bot):
    """
    Генерирует и отправляет отчёты по всем активным магазинам всем подписчикам.
    Вызывается планировщиком.
    """
    subscribers = await get_subscribers()
    if not subscribers:
        logger.warning("Нет подписчиков для рассылки отчётов")
        return

    stores = await get_stores()
    if not stores:
        logger.warning("Нет активных магазинов для отчёта")
        return

    logger.info(f"Генерация отчётов для {len(stores)} магазинов, подписчиков: {len(subscribers)}")

    # Шапка рассылки
    tz = MSK_TZ
    now = datetime.now(tz)
    report_time = await get_setting('report_time', DEFAULT_REPORT_TIME)
    store_names = ", ".join(store_display_name(s) for s in stores)

    months_ru = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }
    date_str = f"{now.day} {months_ru[now.month]} {now.year}"

    header = (
        f"📊 <b>Ежедневный отчёт WB</b>\n"
        f"{date_str} · {report_time} МСК\n\n"
        f"🏪 {store_names}"
    )
    for chat_id in subscribers:
        await bot.send_message(chat_id, header, parse_mode="HTML")

    # Параметры расчёта (один раз для всех магазинов)
    days_threshold = int(await get_setting('calc_days_threshold', '7'))
    threshold_a = float(await get_setting('calc_threshold_a', '4.0'))
    threshold_b = float(await get_setting('calc_threshold_b', '0.5'))
    threshold_c = float(await get_setting('calc_threshold_c', '0.2'))

    # Отчёт по каждому магазину + накопление данных для сводного
    all_stores_data = {}   # {store_name: product_rows}
    all_warehouse_data = {}  # {store_name: warehouse_rows}

    for store in stores:
        name = store_display_name(store)
        try:
            # 1. Загрузка данных из API (или из кэша если свежие)
            product_rows = await fetch_or_cache_product(
                store['id'], store['token'], days_threshold, threshold_a, threshold_b,
            )

            # 2. Загрузка данных по складам
            warehouse_rows = await fetch_or_cache_warehouse(store['id'], store['token'])

            # Накапливаем для сводного отчёта
            all_stores_data[name] = product_rows
            all_warehouse_data[name] = warehouse_rows

            # 3. Генерация Excel из данных
            report_path = await asyncio.to_thread(
                generate_report_from_data, product_rows=product_rows, store_name=name,
                days_threshold=days_threshold, threshold_a=threshold_a, threshold_b=threshold_b,
                threshold_c=threshold_c, warehouse_rows=warehouse_rows,
            )
            await save_report_history(store['id'], report_path)

            document = FSInputFile(report_path, filename=os.path.basename(report_path))
            for chat_id in subscribers:
                await bot.send_document(
                    chat_id=chat_id,
                    document=document,
                    caption=f"📄 {name}"
                )
            logger.info(f"Отчёт для {name} отправлен {len(subscribers)} подписчикам")

        except WBTokenError as e:
            for chat_id in subscribers:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🔑 <b>Ошибка токена: {name}</b>\n\n"
                        f"{e}\n\n"
                        "Обновите токен: /menu → ⚙️ Настройки → Магазины"
                    ),
                    parse_mode="HTML"
                )
            logger.error(f"Ошибка токена для {name}: {e}")

        except Exception as e:
            for chat_id in subscribers:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Ошибка отчёта для {name}: {e}"
                )
            logger.error(f"Ошибка отчёта для {name}: {e}", exc_info=True)

    # Сводный отчёт по всем магазинам (если данные есть хотя бы по 2 магазинам)
    if len(all_stores_data) >= 2:
        try:
            summary_path = await asyncio.to_thread(
                generate_summary_report,
                all_stores_data=all_stores_data,
                all_warehouse_data=all_warehouse_data,
                days_threshold=days_threshold,
                threshold_a=threshold_a,
                threshold_b=threshold_b,
                threshold_c=threshold_c,
            )
            if summary_path:
                document = FSInputFile(summary_path, filename=os.path.basename(summary_path))
                for chat_id in subscribers:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=document,
                        caption="📊 Сводный отчёт по всем магазинам"
                    )
                logger.info(f"Сводный отчёт отправлен {len(subscribers)} подписчикам")
            else:
                logger.info("Сводный отчёт не сгенерирован (нет общих позиций)")
        except Exception as e:
            for chat_id in subscribers:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Ошибка сводного отчёта: {e}"
                )
            logger.error(f"Ошибка сводного отчёта: {e}", exc_info=True)


def reschedule_daily_reports(time_str: str):
    """Перепланирует задачу без перезапуска бота."""
    if _scheduler is None:
        logger.warning("Планировщик не инициализирован, перепланирование невозможно")
        return
    hour, minute = map(int, time_str.split(':'))
    _scheduler.reschedule_job(
        'daily_reports',
        trigger=CronTrigger(hour=hour, minute=minute, timezone=MSK_TZ)
    )
    logger.info(f"Планировщик перепланирован: отчёты в {time_str} {TIMEZONE}")


async def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Настраивает и запускает планировщик."""
    global _scheduler, _bot
    _bot = bot
    _scheduler = AsyncIOScheduler(timezone=MSK_TZ)

    report_time = await get_setting('report_time', DEFAULT_REPORT_TIME)
    hour, minute = map(int, report_time.split(':'))

    _scheduler.add_job(
        send_daily_reports,
        CronTrigger(hour=hour, minute=minute),
        args=[bot],
        id='daily_reports',
        replace_existing=True
    )

    _scheduler.add_job(
        _touch_health,
        'interval',
        seconds=300,
        id='healthcheck',
        replace_existing=True
    )

    _scheduler.start()
    await _touch_health()
    logger.info(f"Планировщик запущен. Отчёты в {report_time} {TIMEZONE}")
    return _scheduler
