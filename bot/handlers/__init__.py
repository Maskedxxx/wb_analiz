"""
Регистрация всех роутеров бота.
"""

from aiogram import Dispatcher

from bot.handlers.menu import router as menu_router
from bot.handlers.analysis import router as analysis_router
from bot.handlers.settings import router as settings_router
from bot.handlers.stores import router as stores_router
from bot.handlers.feedback import router as feedback_router


def register_routers(dp: Dispatcher):
    """Подключает все роутеры к диспетчеру."""
    dp.include_router(menu_router)
    dp.include_router(analysis_router)
    dp.include_router(stores_router)
    dp.include_router(settings_router)
    dp.include_router(feedback_router)  # feedback последним — catch-all
