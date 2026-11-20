"""Publish one quiz. Called by the runner, not by APScheduler."""

from aiogram import Bot

from app.bot.poster import RateLimitedSender
from app.db.models.chats import Chat
from app.db.models.jobs import Job
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.quizzes import QuizRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.jobs.gate import block_reason
from app.jobs.runner import JobCancel
from app.services.access import AccessService
from app.services.lifecycle import ChatLifecycleService
from app.services.profiles import ProfileService
from app.services.quiz_mode import QUIZ
from app.services.quiz_publish import QuizPublisher
from app.services.quizgen import QuizGenerator

__all__ = ["QUIZ", "QuizHandler"]


class QuizHandler:
    """Generate a quiz from published posts, post it, then count the generation."""

    def __init__(
        self,
        chats: ChatRepository,
        users: UserRepository,
        profiles: ProfileService,
        access: AccessService,
        usage: UsageRepository,
        content: ContentRepository,
        quizzes: QuizRepository,
        generator: QuizGenerator,
        sender: RateLimitedSender,
        bot: Bot,
        lifecycle: ChatLifecycleService,
    ) -> None:
        self._chats = chats
        self._users = users
        self._profiles = profiles
        self._access = access
        self._content = content
        self._quizzes = quizzes
        self._generator = generator
        self._publisher = QuizPublisher(quizzes, content, usage, sender, bot, lifecycle)

    async def handle(self, job: Job) -> None:
        """Run one quiz job or raise JobCancel / a transient error."""
        chat, owner = await self._load(job)
        profile = await self._profiles.get(chat.id)
        reason = block_reason(
            active=chat.is_active,
            allowed=await self._access.is_module_allowed(chat, QUIZ),
            has_profile=profile is not None,
            quota=await self._access.remaining_ai_quota(owner),
        )
        if reason is not None or profile is None:
            raise JobCancel(reason or "profile")
        sources = await self._content.latest(chat.id)
        if not sources:
            raise JobCancel("content")
        slot = str((job.payload or {}).get("slot") or "")
        recent = await self._quizzes.recent_questions(chat.id)
        draft = await self._generator.draft(profile, [row.body for row in sources], slot, recent)
        lang = profile.language or "uz"
        await self._publisher.publish(chat, owner, lang, draft, sources[0].id)

    async def _load(self, job: Job) -> tuple[Chat, User]:
        chat = await self._chats.get_by_id(job.chat_id or 0)
        if chat is None:
            raise JobCancel("inactive")
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            raise JobCancel("inactive")
        return chat, owner
