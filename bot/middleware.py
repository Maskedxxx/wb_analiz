"""
Middleware авторизации и rate limiting.
"""

import logging
import time

from aiogram import BaseMiddleware

from bot.config import BOT_PASSWORD
from bot.db import is_authorized
from bot.states import MenuStates

logger = logging.getLogger(__name__)

# Rate limiting: макс. запросов в окне
_RATE_LIMIT = 20          # запросов
_RATE_WINDOW = 60         # секунд
_rate_data: dict[int, list[float]] = {}
_last_cleanup: float = 0
_CLEANUP_INTERVAL = 300   # очистка устаревших записей каждые 5 минут


def _is_rate_limited(user_id: int) -> bool:
    """Проверяет, превышен ли лимит запросов для пользователя."""
    global _last_cleanup
    now = time.monotonic()

    # Периодическая очистка устаревших записей (предотвращает утечку памяти)
    if now - _last_cleanup > _CLEANUP_INTERVAL:
        stale = [uid for uid, ts in _rate_data.items() if not ts or now - ts[-1] >= _RATE_WINDOW]
        for uid in stale:
            del _rate_data[uid]
        _last_cleanup = now

    timestamps = _rate_data.get(user_id, [])
    # Убираем старые записи
    timestamps = [t for t in timestamps if now - t < _RATE_WINDOW]
    timestamps.append(now)
    _rate_data[user_id] = timestamps
    return len(timestamps) > _RATE_LIMIT


class AuthMiddleware(BaseMiddleware):
    """Блокирует неавторизованных пользователей + rate limiting."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Rate limiting (для всех пользователей)
        if _is_rate_limited(user.id):
            logger.warning(f"Rate limit exceeded for user {user.id}")
            if hasattr(event, 'answer'):
                await event.answer("⏳ Слишком много запросов. Подождите минуту.", show_alert=True)
            return

        # Если пароль не задан — пропускаем всех (режим разработки)
        if not BOT_PASSWORD:
            return await handler(event, data)

        # Если авторизован — пропускаем
        if await is_authorized(user.id):
            return await handler(event, data)

        # Если в состоянии ввода пароля — пропускаем к хендлеру
        state = data.get("state")
        if state:
            current = await state.get_state()
            if current == MenuStates.waiting_password.state:
                return await handler(event, data)

        # Если это команда /start — пропускаем к хендлеру
        if hasattr(event, 'text') and event.text and event.text.startswith('/start'):
            return await handler(event, data)

        # Всё остальное — блокируем
        logger.debug(f"Blocked request from unauthorized user {user.id}")
        if hasattr(event, 'answer'):
            await event.answer("🔒 Доступ ограничен. Введите /start для авторизации.")
        return
