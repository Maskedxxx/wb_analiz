"""
Точка входа телеграм-бота WB Analiz.

Запускает бота с интерактивным меню и планировщиком отчётов.
"""

import asyncio
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import TELEGRAM_TOKEN, BOT_PASSWORD, LOGS_DIR, REPORT_RETENTION_DAYS, LOG_RETENTION_DAYS
from bot.handlers import register_routers
from bot.handlers.feedback import cleanup_old_feedback
from bot.db import init_db, cleanup_old_reports, migrate_trademarks
from bot.core.middleware import AuthMiddleware
from bot.services.scheduler import setup_scheduler
from bot.core.security import TokenMaskFilter

# Создаём директорию для логов
os.makedirs(LOGS_DIR, exist_ok=True)

# Логирование в консоль и файл с ежедневной ротацией
_log_handler = TimedRotatingFileHandler(
    os.path.join(LOGS_DIR, 'bot.log'),
    when='midnight',
    interval=1,
    backupCount=LOG_RETENTION_DAYS,
    encoding='utf-8',
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        _log_handler,
    ]
)
# Фильтр маскировки токенов во всех логах
logging.getLogger().addFilter(TokenMaskFilter())
logger = logging.getLogger(__name__)


async def main():
    """Основная функция запуска бота."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан!")
        sys.exit(1)

    # Инициализация БД (создание таблиц + автомиграция токена из env)
    await init_db()
    await migrate_trademarks()
    cleanup_old_feedback()
    deleted = await cleanup_old_reports(REPORT_RETENTION_DAYS)
    if deleted:
        logger.info(f"Удалено устаревших отчётов: {deleted}")

    # Инициализация бота и диспетчера
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware авторизации
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    if not BOT_PASSWORD:
        logger.warning("BOT_PASSWORD не задан — авторизация отключена, бот открыт для всех")

    # Подключение роутеров
    register_routers(dp)

    # Планировщик
    scheduler = await setup_scheduler(bot)

    # Запуск polling
    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        # Graceful shutdown: каждый ресурс закрываем отдельно,
        # чтобы ошибка в одном не блокировала остальные
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("Ошибка при остановке планировщика")
        try:
            await bot.session.close()
        except Exception:
            logger.exception("Ошибка при закрытии сессии бота")


if __name__ == '__main__':
    asyncio.run(main())
