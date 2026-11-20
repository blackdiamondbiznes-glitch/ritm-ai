"""Private notices. Never log the message body."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def notify_user(
    bot: Bot,
    telegram_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Send one private HTML message. False when the user cannot be reached."""
    try:
        await bot.send_message(telegram_id, text, reply_markup=markup)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        logger.info("notify failed telegram_id=%s", telegram_id)
        return False
