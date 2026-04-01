"""
Утилиты для работы с сообщениями бота.
"""

from aiogram import Bot


async def edit_or_send(
    bot: Bot,
    chat_id: int,
    bot_msg_id: int | None,
    text: str,
    reply_markup=None,
):
    """Редактирует существующее сообщение бота или отправляет новое (fallback)."""
    if bot_msg_id:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=bot_msg_id,
                reply_markup=reply_markup, parse_mode="HTML",
            )
            return
        except Exception:
            pass
    await bot.send_message(
        chat_id, text, reply_markup=reply_markup, parse_mode="HTML",
    )
