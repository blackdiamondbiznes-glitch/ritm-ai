"""Filter an admin post, store it, and enqueue a delayed quiz job."""

from datetime import timedelta

from app.db.models.chats import Chat
from app.db.models.content import ContentItem, ContentKind
from app.db.models.jobs import Job, JobStatus
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.clock import Clock, utcnow
from app.services.profiles import ProfileService
from app.services.quiz_mode import ADMIN_POST_QUIZ

FORWARD = "forward"
EMPTY = "empty"
SHORT = "short"
BOT = "bot"
INACTIVE = "inactive"
PROFILE = "profile"
MODULE = "module"
DISABLED = "disabled"
QUOTA = "quota"
DUPLICATE = "duplicate"


def post_body(text: str | None, caption: str | None, *, forwarded: bool) -> str | None:
    """Return the usable post text, or None for a forward or media without a caption."""
    if forwarded:
        return None
    body = (text or caption or "").strip()
    return body or None


def skip_reason(
    *,
    body: str | None,
    min_chars: int,
    from_bot: bool,
    active: bool,
    has_profile: bool,
    allowed: bool,
    module_enabled: bool,
    quota: int,
) -> str | None:
    """Why this post must not start a quiz job, or None when it may."""
    if from_bot:
        return BOT
    if body is None:
        return EMPTY
    if len(body) < min_chars:
        return SHORT
    if not active:
        return INACTIVE
    if not has_profile:
        return PROFILE
    if not allowed:
        return MODULE
    if not module_enabled:
        return DISABLED
    if quota <= 0:
        return QUOTA
    return None


class AdminPostService:
    """The handler only collects facts. Access and the queue live here."""

    def __init__(
        self,
        chats: ChatRepository,
        users: UserRepository,
        access: AccessService,
        profiles: ProfileService,
        content: ContentRepository,
        jobs: JobRepository,
        audit: AuditRepository,
        *,
        min_chars: int,
        delay_seconds: int,
        now: Clock | None = None,
    ) -> None:
        self._chats = chats
        self._users = users
        self._access = access
        self._profiles = profiles
        self._content = content
        self._jobs = jobs
        self._audit = audit
        self._min_chars = min_chars
        self._delay = delay_seconds
        self._now = now or utcnow

    async def ingest(
        self,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
        body: str | None,
        from_bot: bool,
    ) -> str | None:
        """Store the post and enqueue one delayed job. Return a skip code, or None."""
        chat = await self._chats.get_by_telegram_id(telegram_chat_id)
        if chat is None or not chat.is_active:
            return INACTIVE
        profile = await self._profiles.get(chat.id)
        owner = await self._users.get_by_id(chat.owner_id)
        quota = 0 if owner is None else await self._access.remaining_ai_quota(owner)
        allowed = await self._access.is_module_allowed(chat, ADMIN_POST_QUIZ)
        enabled = bool(profile and ADMIN_POST_QUIZ in (profile.modules_enabled or []))
        reason = skip_reason(
            body=body,
            min_chars=self._min_chars,
            from_bot=from_bot,
            active=chat.is_active,
            has_profile=profile is not None,
            allowed=allowed,
            module_enabled=enabled,
            quota=quota,
        )
        if reason is not None or body is None:
            return reason
        existing = await self._content.get_by_telegram_id(chat.id, telegram_message_id)
        if existing is not None and existing.kind != ContentKind.ADMIN_POST:
            return BOT
        item = existing or await self._store(chat, telegram_message_id, body)
        return await self._enqueue(chat, item)

    async def _store(self, chat: Chat, telegram_message_id: int, body: str) -> ContentItem:
        return await self._content.add(
            ContentItem(
                chat_id=chat.id,
                kind=ContentKind.ADMIN_POST,
                body=body,
                meta={"telegram_message_id": telegram_message_id},
                telegram_message_id=telegram_message_id,
                published_at=self._now(),
            )
        )

    async def _enqueue(self, chat: Chat, item: ContentItem) -> str | None:
        if await self._jobs.has_for_content(ADMIN_POST_QUIZ, item.id):
            return DUPLICATE
        job = Job(
            chat_id=chat.id,
            type=ADMIN_POST_QUIZ,
            payload={"content_item_id": item.id},
            run_at=self._now() + timedelta(seconds=self._delay),
            status=JobStatus.PENDING,
            attempts=0,
            max_attempts=5,
        )
        await self._jobs.add(job)
        await self._audit.add(
            actor_user_id=chat.owner_id,
            action="admin_post_quiz_queued",
            entity="content_item",
            entity_id=str(item.id),
            data={"chat_id": chat.id, "telegram_message_id": item.telegram_message_id},
        )
        return None
