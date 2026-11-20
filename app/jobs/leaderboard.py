"""Weekly Top-10 announcement. No AI call and no quota spend."""

import logging

from aiogram import Bot

from app.bot.copy import board_announcement
from app.bot.poster import ChatGone, RateLimitedSender
from app.db.models.chats import Chat
from app.db.models.jobs import Job
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.db.repositories.users import UserRepository
from app.jobs.runner import JobCancel
from app.services.access import AccessService
from app.services.leaderboard import MODULE, LeaderboardService
from app.services.lifecycle import ChatLifecycleService
from app.services.profiles import ProfileService

logger = logging.getLogger(__name__)


class LeaderboardHandler:
    """Post the previous week's Top-10, or a live board when asked."""

    def __init__(
        self,
        chats: ChatRepository,
        users: UserRepository,
        profiles: ProfileService,
        access: AccessService,
        boards: LeaderboardService,
        sender: RateLimitedSender,
        bot: Bot,
        lifecycle: ChatLifecycleService,
    ) -> None:
        self._chats = chats
        self._users = users
        self._profiles = profiles
        self._access = access
        self._boards = boards
        self._sender = sender
        self._bot = bot
        self._lifecycle = lifecycle

    async def handle(self, job: Job) -> None:
        """Announce once per finished week. An empty week is a quiet skip."""
        chat, _owner = await self._load(job)
        profile = await self._profiles.get(chat.id)
        allowed = await self._access.is_module_allowed(chat, MODULE)
        if not chat.is_active:
            raise JobCancel("inactive")
        if profile is None:
            raise JobCancel("profile")
        if not allowed:
            raise JobCancel("module")
        window = str((job.payload or {}).get("window") or "previous")
        lang = profile.language or "uz"
        zone = profile.timezone
        status, view, period = await self._boards.prepare(chat, zone, window=window)
        if status == "already":
            logger.info("leaderboard skip chat_id=%s reason=already", chat.id)
            return
        if status == "empty" or view is None:
            logger.info("leaderboard skip chat_id=%s reason=empty", chat.id)
            return
        message_id = await self._send(chat, board_announcement(view, lang))
        if period is not None:
            await self._boards.remember(period, message_id)

    async def _load(self, job: Job) -> tuple[Chat, User]:
        chat = await self._chats.get_by_id(job.chat_id or 0)
        if chat is None:
            raise JobCancel("inactive")
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            raise JobCancel("inactive")
        return chat, owner

    async def _send(self, chat: Chat, text: str) -> int:
        try:
            return await self._sender.post(self._bot, chat.telegram_chat_id, text)
        except ChatGone:
            await self._lifecycle.mark_bot_removed(chat.telegram_chat_id)
            raise JobCancel("gone") from None
