"""Outbound messages. Wait on 429. Never log the payload."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)
_MAX_WAIT = 60


async def notify(
    bot: Bot,
    telegram_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Send a private message. Returns False when Telegram refuses."""
    try:
        await _send(bot, telegram_id, text, markup)
        return True
    except TelegramAPIError:
        logger.info("notify failed user_id=%s", telegram_id)
        return False


async def _send(
    bot: Bot,
    telegram_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    try:
        await bot.send_message(telegram_id, text, reply_markup=markup)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(min(exc.retry_after, _MAX_WAIT))
        await bot.send_message(telegram_id, text, reply_markup=markup)
