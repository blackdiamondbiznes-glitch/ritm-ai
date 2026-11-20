"""Turn one stored admin post into two or three quizzes."""

from aiogram import Bot

from app.bot.poster import RateLimitedSender
from app.db.models.chats import Chat
from app.db.models.content import ContentItem, ContentKind
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
from app.services.quiz_mode import ADMIN_POST_QUIZ
from app.services.quiz_publish import QuizPublisher
from app.services.quizgen import QuizGenerator


class AdminPostQuizHandler:
    """Generate a batch, publish each quiz, then charge quota once."""

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
        """Run one admin-post quiz job or raise JobCancel / a transient error."""
        chat, owner, item = await self._load(job)
        profile = await self._profiles.get(chat.id)
        enabled = bool(profile and ADMIN_POST_QUIZ in (profile.modules_enabled or []))
        reason = block_reason(
            active=chat.is_active,
            allowed=await self._access.is_module_allowed(chat, ADMIN_POST_QUIZ) and enabled,
            has_profile=profile is not None,
            quota=await self._access.remaining_ai_quota(owner),
        )
        if reason is not None or profile is None:
            raise JobCancel(reason or "profile")
        lang = profile.language or "uz"
        already = int((job.payload or {}).get("published") or 0)
        recent = await self._quizzes.recent_questions(chat.id)
        drafts = await self._generator.draft_from_admin_post(profile, item.body, recent)
        for index, draft in enumerate(drafts):
            if index < already:
                continue
            await self._publisher.publish(chat, owner, lang, draft, item.id, charge=False)
            _mark(job, "published", index + 1)
        if not (job.payload or {}).get("charged"):
            await self._publisher.charge(owner)
            _mark(job, "charged", True)

    async def _load(self, job: Job) -> tuple[Chat, User, ContentItem]:
        chat = await self._chats.get_by_id(job.chat_id or 0)
        if chat is None:
            raise JobCancel("inactive")
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            raise JobCancel("inactive")
        item_id = int((job.payload or {}).get("content_item_id") or 0)
        item = await self._content.get(item_id)
        if item is None or item.kind != ContentKind.ADMIN_POST or item.chat_id != chat.id:
            raise JobCancel("content")
        return chat, owner, item


def _mark(job: Job, key: str, value: object) -> None:
    payload = dict(job.payload or {})
    payload[key] = value
    job.payload = payload
