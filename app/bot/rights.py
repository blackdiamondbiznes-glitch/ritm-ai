"""Load chat members, retrying once on Telegram flood control."""

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Chat, ChatMember

_MAX_WAIT = 60


async def load_member_facts(
    bot: Bot,
    bot_id: int,
    telegram_chat_id: int,
    user_telegram_id: int,
) -> tuple[Chat, ChatMember, ChatMember]:
    """getChat + two getChatMember calls. One retry on 429."""
    try:
        return await _fetch(bot, bot_id, telegram_chat_id, user_telegram_id)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(min(exc.retry_after, _MAX_WAIT))
        return await _fetch(bot, bot_id, telegram_chat_id, user_telegram_id)


async def _fetch(
    bot: Bot,
    bot_id: int,
    telegram_chat_id: int,
    user_telegram_id: int,
) -> tuple[Chat, ChatMember, ChatMember]:
    tg_chat = await bot.get_chat(telegram_chat_id)
    user_member = await bot.get_chat_member(telegram_chat_id, user_telegram_id)
    bot_member = await bot.get_chat_member(telegram_chat_id, bot_id)
    return tg_chat, user_member, bot_member
