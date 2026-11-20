"""Connect, disconnect and bot-removal rules."""

from dataclasses import dataclass

from app.db.models.chats import Chat, ChatType
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.services.access import AccessService
from app.services.clock import Clock, utcnow
from app.services.trial import TrialService


@dataclass(frozen=True)
class ConnectOutcome:
    """What the connect handler should tell the owner."""

    ok: bool
    code: str
    chat_id: int | None = None
    trial_started: bool = False
    used: int = 0
    limit: int = 0


class ChatLifecycleService:
    """Ownership-safe connect and disconnect."""

    def __init__(
        self,
        chats: ChatRepository,
        access: AccessService,
        trial: TrialService,
        audit: AuditRepository,
        now: Clock | None = None,
    ) -> None:
        self._chats = chats
        self._access = access
        self._trial = trial
        self._audit = audit
        self._now = now or utcnow

    async def connect(
        self,
        owner: User,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str,
        username: str | None,
        user_is_admin: bool,
        bot_can_post: bool,
    ) -> ConnectOutcome:
        """Link a chat after the caller has checked Telegram rights."""
        if not user_is_admin:
            return ConnectOutcome(False, "not_admin")
        if not bot_can_post:
            return ConnectOutcome(False, "bot_rights")
        existing = await self._chats.get_by_telegram_id(telegram_chat_id)
        if existing is not None and existing.is_active and existing.owner_id != owner.id:
            return ConnectOutcome(False, "owned")
        if existing is not None and existing.is_active and existing.owner_id == owner.id:
            return ConnectOutcome(True, "already", chat_id=existing.id)
        decision = await self._access.can_connect_chat(owner)
        if not decision.allowed:
            return ConnectOutcome(False, "limit", used=decision.used, limit=decision.limit)
        chat = await self._save_chat(
            existing,
            owner,
            telegram_chat_id=telegram_chat_id,
            chat_type=chat_type,
            title=title,
            username=username,
        )
        started = await self._trial.start_if_eligible(owner, chat)
        await self._audit.add(
            actor_user_id=owner.id,
            action="chat_connected",
            entity="chat",
            entity_id=str(chat.id),
            data={"telegram_chat_id": telegram_chat_id, "trial": started},
        )
        code = "trial" if started else "linked"
        return ConnectOutcome(True, code, chat_id=chat.id, trial_started=started)

    async def disconnect(self, owner: User, chat: Chat) -> None:
        """Deactivate a chat. Does not reset `trial_consumed`."""
        chat.is_active = False
        chat.removed_at = self._now()
        await self._audit.add(
            actor_user_id=owner.id,
            action="chat_disconnected",
            entity="chat",
            entity_id=str(chat.id),
            data={"telegram_chat_id": chat.telegram_chat_id, "reason": "owner"},
        )

    async def mark_bot_removed(self, telegram_chat_id: int) -> Chat | None:
        """Bot left or was kicked. Returns the chat when it changed."""
        chat = await self._chats.get_by_telegram_id(telegram_chat_id)
        if chat is None or not chat.is_active:
            return None
        chat.is_active = False
        chat.removed_at = self._now()
        await self._audit.add(
            actor_user_id=chat.owner_id,
            action="chat_disconnected",
            entity="chat",
            entity_id=str(chat.id),
            data={"telegram_chat_id": telegram_chat_id, "reason": "bot_removed"},
        )
        return chat

    async def _save_chat(
        self,
        existing: Chat | None,
        owner: User,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str,
        username: str | None,
    ) -> Chat:
        parsed = ChatType(chat_type)
        if existing is None:
            return await self._chats.add(
                Chat(
                    telegram_chat_id=telegram_chat_id,
                    type=parsed,
                    title=title[:255],
                    username=username,
                    owner_id=owner.id,
                    is_active=True,
                    trial_consumed=False,
                    added_at=self._now(),
                )
            )
        existing.owner_id = owner.id
        existing.type = parsed
        existing.title = title[:255]
        existing.username = username
        existing.is_active = True
        existing.removed_at = None
        existing.added_at = self._now()
        return existing
