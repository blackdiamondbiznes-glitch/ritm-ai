"""Super-admin actions: stats, grants, blocks."""

from dataclasses import dataclass
from datetime import timedelta

from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.services.clock import Clock, utcnow

_MAX_GRANT_DAYS = 3650


@dataclass(frozen=True)
class Stats:
    """Platform counters for the admin screen."""

    users: int
    chats: int
    trials: int
    paid: int


class AdminError(Exception):
    """Admin action rejected. `code` is safe to map to a locale key."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AdminService:
    """Mutations that only a super admin may trigger."""

    def __init__(
        self,
        users: UserRepository,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        chats: ChatRepository,
        audit: AuditRepository,
        now: Clock | None = None,
    ) -> None:
        self._users = users
        self._plans = plans
        self._subs = subscriptions
        self._chats = chats
        self._audit = audit
        self._now = now or utcnow

    async def stats(self) -> Stats:
        """Global counts. Trials and paid rows ignore already-expired dates."""
        now = self._now()
        return Stats(
            users=await self._users.count(),
            chats=await self._chats.count_all(),
            trials=await self._subs.count_open_trials(now),
            paid=await self._subs.count_open_paid(now),
        )

    async def grant(
        self, actor: User, telegram_id: int, plan_code: str, days: int, reason: str = ""
    ) -> User:
        """Replace any open subscription with an admin grant."""
        if days < 1 or days > _MAX_GRANT_DAYS:
            raise AdminError("bad_days")
        target = await self._users.get_by_telegram_id(telegram_id)
        if target is None:
            raise AdminError("missing_user")
        plan = await self._plans.get_by_code(plan_code)
        if plan is None or not plan.is_active:
            raise AdminError("bad_plan")
        await self._cancel_open(target.id)
        now = self._now()
        created = await self._subs.add(
            Subscription(
                owner_id=target.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now,
                expires_at=now + timedelta(days=days),
            )
        )
        await self._audit.add(
            actor_user_id=actor.id,
            action="plan_granted",
            entity="subscription",
            entity_id=str(created.id),
            data={
                "telegram_id": telegram_id,
                "plan": plan.code,
                "days": days,
                "reason": (reason or "").strip()[:500],
            },
        )
        return target

    async def extend(self, actor: User, telegram_id: int, days: int, reason: str) -> User:
        """Add days to the owner's open, unexpired subscription. Plan stays the same."""
        if days < 1 or days > _MAX_GRANT_DAYS:
            raise AdminError("bad_days")
        text = (reason or "").strip()[:500]
        if not text:
            raise AdminError("reason")
        target = await self._users.get_by_telegram_id(telegram_id)
        if target is None:
            raise AdminError("missing_user")
        open_sub = await self._subs.get_open(target.id)
        if open_sub is None or open_sub.expires_at <= self._now():
            raise AdminError("no_open")
        before = open_sub.expires_at
        open_sub.expires_at = before + timedelta(days=days)
        await self._audit.add(
            actor_user_id=actor.id,
            action="plan_extended",
            entity="subscription",
            entity_id=str(open_sub.id),
            data={
                "telegram_id": telegram_id,
                "days": days,
                "reason": text,
                "from": before.isoformat(),
                "to": open_sub.expires_at.isoformat(),
            },
        )
        return target

    async def set_blocked(self, actor: User, telegram_id: int, blocked: bool) -> User:
        """Block or unblock. Writes an audit row either way."""
        target = await self._users.get_by_telegram_id(telegram_id)
        if target is None:
            raise AdminError("missing_user")
        target.is_blocked = blocked
        action = "user_blocked" if blocked else "user_unblocked"
        await self._audit.add(
            actor_user_id=actor.id,
            action=action,
            entity="user",
            entity_id=str(target.id),
            data={"telegram_id": telegram_id},
        )
        return target

    async def _cancel_open(self, owner_id: int) -> None:
        open_sub = await self._subs.get_open(owner_id)
        if open_sub is not None:
            open_sub.status = SubscriptionStatus.CANCELED
