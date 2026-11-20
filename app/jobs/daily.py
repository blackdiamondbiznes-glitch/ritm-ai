"""Publish one daily post. Called by the runner, not by APScheduler."""

from html import escape

from aiogram import Bot

from app.bot.poster import ChatGone, RateLimitedSender
from app.db.models.chats import Chat
from app.db.models.content import ContentItem, ContentKind
from app.db.models.jobs import Job
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.jobs.gate import block_reason
from app.jobs.runner import JobCancel
from app.services.access import AI_METRIC, AccessService
from app.services.clock import Clock, utcnow
from app.services.generate import ContentGenerator, Draft
from app.services.lifecycle import ChatLifecycleService
from app.services.profiles import ProfileService


class DailyHandler:
    """Generate, send, then count the generation."""

    def __init__(
        self,
        chats: ChatRepository,
        users: UserRepository,
        profiles: ProfileService,
        access: AccessService,
        usage: UsageRepository,
        content: ContentRepository,
        generator: ContentGenerator,
        sender: RateLimitedSender,
        bot: Bot,
        lifecycle: ChatLifecycleService,
        now: Clock | None = None,
    ) -> None:
        self._chats = chats
        self._users = users
        self._profiles = profiles
        self._access = access
        self._usage = usage
        self._content = content
        self._generator = generator
        self._sender = sender
        self._bot = bot
        self._lifecycle = lifecycle
        self._now = now or utcnow

    async def handle(self, job: Job) -> None:
        """Run one daily_content job or raise JobCancel / a transient error."""
        chat, owner = await self._load(job)
        profile = await self._profiles.get(chat.id)
        allowed = await self._access.is_module_allowed(chat, "daily_content")
        quota = await self._access.remaining_ai_quota(owner)
        reason = block_reason(
            active=chat.is_active,
            allowed=allowed,
            has_profile=profile is not None,
            quota=quota,
        )
        if reason is not None or profile is None:
            raise JobCancel(reason or "profile")
        slot = str((job.payload or {}).get("slot") or "")
        recent = await self._content.recent_bodies(chat.id)
        draft = await self._generator.draft(profile, slot, recent)
        message_id = await self._send(chat, draft.body)
        await self._store(chat, owner, draft, slot, message_id)

    async def _load(self, job: Job) -> tuple[Chat, User]:
        chat = await self._chats.get_by_id(job.chat_id or 0)
        if chat is None:
            raise JobCancel("inactive")
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            raise JobCancel("inactive")
        return chat, owner

    async def _send(self, chat: Chat, body: str) -> int:
        try:
            return await self._sender.post(self._bot, chat.telegram_chat_id, escape(body)[:4000])
        except ChatGone:
            await self._lifecycle.mark_bot_removed(chat.telegram_chat_id)
            raise JobCancel("gone") from None

    async def _store(
        self, chat: Chat, owner: User, draft: Draft, slot: str, message_id: int
    ) -> None:
        now = self._now()
        await self._usage.bump(owner.id, AI_METRIC, now.strftime("%Y-%m"))
        await self._content.add(
            ContentItem(
                chat_id=chat.id,
                kind=ContentKind.DAILY,
                body=draft.body,
                meta={"provider": draft.provider, "model": draft.model, "slot": slot},
                telegram_message_id=message_id,
                published_at=now,
            )
        )
