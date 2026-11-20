"""Link a chat the bot was added to. Shared by the bot confirm button and the Mini App."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot.members import bot_can_post, map_chat_type, user_is_manager
from app.bot.rights import load_member_facts
from app.db.models.users import User
from app.services.lifecycle import ChatLifecycleService, ConnectOutcome

logger = logging.getLogger(__name__)


async def link_chat(
    bot: Bot,
    bot_id: int,
    telegram_chat_id: int,
    owner: User,
    lifecycle: ChatLifecycleService,
) -> ConnectOutcome:
    """Re-check live Telegram rights, then connect through the lifecycle service."""
    try:
        tg_chat, user_member, bot_member = await load_member_facts(
            bot, bot_id, telegram_chat_id, owner.telegram_id
        )
    except TelegramForbiddenError:
        return ConnectOutcome(False, "bot_rights")
    except TelegramBadRequest:
        logger.info("getChat failed chat_id=%s", telegram_chat_id)
        await lifecycle.mark_bot_removed(telegram_chat_id)
        return ConnectOutcome(False, "gone")
    return await lifecycle.connect(
        owner,
        telegram_chat_id=telegram_chat_id,
        chat_type=map_chat_type(tg_chat.type),
        title=tg_chat.title or "Chat",
        username=tg_chat.username,
        user_is_admin=user_is_manager(user_member),
        bot_can_post=bot_can_post(bot_member),
    )
