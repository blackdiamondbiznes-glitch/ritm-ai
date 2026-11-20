"""One trial per owner and one trial per chat."""

from datetime import timedelta

from app.db.models.chats import Chat
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.clock import Clock, utcnow


class TrialService:
    """Starts the full-feature trial or refuses when it was already used."""

    def __init__(
        self,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        audit: AuditRepository,
        trial_days: int,
        now: Clock | None = None,
    ) -> None:
        self._plans = plans
        self._subs = subscriptions
        self._audit = audit
        self._trial_days = trial_days
        self._now = now or utcnow

    async def start_if_eligible(self, owner: User, chat: Chat) -> bool:
        """Create a pro trial subscription. Returns False when the trial is spent."""
        if owner.trial_used_at is not None or chat.trial_consumed:
            return False
        if not await self._close_expired_open(owner.id):
            return False
        pro = await self._plans.get_by_code("pro")
        if pro is None:
            raise RuntimeError("pro plan is not seeded")
        now = self._now()
        expires = now + timedelta(days=self._trial_days)
        await self._subs.add(
            Subscription(
                owner_id=owner.id,
                plan_id=pro.id,
                status=SubscriptionStatus.TRIAL,
                source=SubscriptionSource.TRIAL,
                started_at=now,
                expires_at=expires,
            )
        )
        owner.trial_used_at = now
        chat.trial_consumed = True
        await self._audit.add(
            actor_user_id=owner.id,
            action="trial_started",
            entity="subscription",
            entity_id=str(owner.id),
            data={"chat_id": chat.id, "days": self._trial_days, "plan": "pro"},
        )
        return True

    async def _close_expired_open(self, owner_id: int) -> bool:
        """Expire a stale open row so a new trial can be inserted. False if still valid."""
        open_sub = await self._subs.get_open(owner_id)
        if open_sub is None:
            return True
        if open_sub.expires_at > self._now():
            return False
        open_sub.status = SubscriptionStatus.EXPIRED
        return True
