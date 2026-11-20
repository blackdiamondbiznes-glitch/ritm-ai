"""Ingest channel posts and group admin messages into the delayed quiz queue."""

import logging

from aiogram import F, Router
from aiogram.types import Message

from app.bot.admin_check import AdminStatusCache, sender_is_admin
from app.services.admin_posts import AdminPostService, post_body

logger = logging.getLogger(__name__)

router = Router(name="admin_posts")


@router.channel_post()
async def on_channel_post(
    message: Message,
    admin_posts: AdminPostService,
    bot_id: int,
) -> None:
    """A post in a connected channel. There is usually no from_user."""
    await _ingest(message, admin_posts, bot_id, is_admin=True)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_post(
    message: Message,
    admin_posts: AdminPostService,
    admin_cache: AdminStatusCache,
    bot: object,
    bot_id: int,
) -> None:
    """A message in a connected group, accepted only from chat administrators."""
    if not await sender_is_admin(bot, admin_cache, message):  # type: ignore[arg-type]
        return
    await _ingest(message, admin_posts, bot_id, is_admin=True)


async def _ingest(
    message: Message,
    admin_posts: AdminPostService,
    bot_id: int,
    *,
    is_admin: bool,
) -> None:
    if not is_admin:
        return
    if message.text and message.text.startswith("/"):
        return
    if getattr(message, "is_automatic_forward", False):
        return
    forwarded = bool(message.forward_origin or message.forward_date)
    from_user = message.from_user
    from_bot = from_user is not None and from_user.id == bot_id
    body = post_body(message.text, message.caption, forwarded=forwarded)
    reason = await admin_posts.ingest(
        telegram_chat_id=message.chat.id,
        telegram_message_id=message.message_id,
        body=body,
        from_bot=from_bot,
    )
    if reason is not None:
        logger.info(
            "admin post skipped chat_id=%s message_id=%s reason=%s",
            message.chat.id,
            message.message_id,
            reason,
        )
