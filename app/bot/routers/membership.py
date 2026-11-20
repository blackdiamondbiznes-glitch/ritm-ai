"""Track the bot being added to or removed from a chat."""

from datetime import UTC, datetime
from html import escape

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated

from app.bot.keyboards.menu import connect_confirm
from app.bot.members import is_promoted, is_removed, map_chat_type
from app.bot.sender import notify
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.services.lifecycle import ChatLifecycleService
from app.services.pending import PendingChat, PendingChatStore

router = Router(name="membership")


@router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    pending: PendingChatStore,
    lifecycle: ChatLifecycleService,
    users: UserRepository,
    lang: str,
) -> None:
    """Record a pending chat, or deactivate when the bot loses admin."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    if is_removed(old, new):
        await _removed(event, bot, lifecycle, users)
        return
    if not is_promoted(old, new) or event.from_user is None:
        return
    title = event.chat.title or "Chat"
    pending.put(
        PendingChat(
            telegram_chat_id=event.chat.id,
            title=title,
            chat_type=map_chat_type(event.chat.type),
            username=event.chat.username,
            added_by_telegram_id=event.from_user.id,
            added_at=datetime.now(UTC),
        )
    )
    text = t("connect_found", lang, title=escape(title))
    await notify(bot, event.from_user.id, text, connect_confirm(lang, event.chat.id))


async def _removed(
    event: ChatMemberUpdated,
    bot: Bot,
    lifecycle: ChatLifecycleService,
    users: UserRepository,
) -> None:
    chat = await lifecycle.mark_bot_removed(event.chat.id)
    if chat is None:
        return
    owner = await users.get_by_id(chat.owner_id)
    if owner is None:
        return
    text = t("bot_removed", owner.language_code, title=escape(chat.title))
    await notify(bot, owner.telegram_id, text)
