"""The only place that answers plan, quota and chat-limit questions."""

import math
from dataclasses import dataclass
from datetime import datetime

from app.db.models.chats import Chat
from app.db.models.plans import Plan
from app.db.models.subscriptions import SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.services.clock import Clock, utcnow


@dataclass(frozen=True)
class FounderOffer:
    """Live founder-slot state for one owner."""

    slots: int
    used: int
    remaining: int
    keep: bool

    @property
    def show_sale(self) -> bool:
        return self.keep or self.remaining > 0


AI_METRIC = "ai_generation"


@dataclass(frozen=True)
class AccessDecision:
    """Result of a chat-limit check."""

    allowed: bool
    used: int
    limit: int


@dataclass(frozen=True)
class TutorLimits:
    """Cabinet caps taken from the effective plan. Trial uses Pro."""

    max_groups: int
    max_students: int
    plan_code: str
    fees: bool


@dataclass(frozen=True)
class PlanSnapshot:
    """What the owner can use right now."""

    plan: Plan
    kind: str
    days_left: int | None
    chats_used: int
    ai_used: int


class AccessService:
    """Resolves the effective plan, including lazy expiry."""

    def __init__(
        self,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        chats: ChatRepository,
        usage: UsageRepository,
        users: UserRepository,
        now: Clock | None = None,
        founder_slots: int = 20,
    ) -> None:
        self._plans = plans
        self._subs = subscriptions
        self._chats = chats
        self._usage = usage
        self._users = users
        self._now = now or utcnow
        self._founder_slots = max(0, founder_slots)

    async def get_effective_plan(self, owner: User) -> Plan:
        """Active unexpired plan, otherwise the free plan."""
        free = await self._require_free()
        sub = await self._subs.get_open(owner.id)
        if sub is None or sub.expires_at <= self._now():
            return free
        plan = await self._plans.get_by_id(sub.plan_id)
        return plan or free

    async def can_connect_chat(self, owner: User) -> AccessDecision:
        """True when the owner still has a free chat slot."""
        plan = await self.get_effective_plan(owner)
        used = await self._chats.count_active(owner.id)
        return AccessDecision(allowed=used < plan.max_chats, used=used, limit=plan.max_chats)

    async def remaining_ai_quota(self, owner: User) -> int:
        """Generations left in the current UTC month."""
        _used, maximum, left = await self._quota(owner)
        return left

    async def count_founders(self) -> int:
        """How many owners already have founder status."""
        return await self._users.count_founders()

    async def offers_founder_price(self, owner: User) -> bool:
        """True when this owner pays the founder rate, now or on approval."""
        if owner.is_founder:
            return True
        return await self.count_founders() < self._founder_slots

    def unit_price(self, plan: Plan, *, founder: bool) -> int:
        """Monthly price used for a request. Founder prices live on the plan row."""
        if founder:
            return int(plan.founder_price_uzs)
        return int(plan.price_uzs)

    async def grant_founder(self, owner: User) -> bool:
        """Mark the owner as a founder when a slot remains. Caller must lock first."""
        if owner.is_founder:
            return True
        if await self.count_founders() >= self._founder_slots:
            return False
        owner.is_founder = True
        owner.founder_since = self._now()
        return True

    async def founder_offer(self, owner: User) -> FounderOffer:
        """Slots left and whether this owner already keeps the founder price."""
        used = await self.count_founders()
        remaining = max(0, self._founder_slots - used)
        return FounderOffer(
            slots=self._founder_slots,
            used=used,
            remaining=remaining,
            keep=bool(owner.is_founder),
        )

    async def is_module_allowed(self, chat: Chat, module: str) -> bool:
        """Whether the chat owner's effective plan includes `module`."""
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            return False
        plan = await self.get_effective_plan(owner)
        return module in (plan.modules or [])

    async def allowed_modules(self, chat: Chat) -> frozenset[str]:
        """All modules the chat owner's effective plan includes, in one lookup."""
        owner = await self._users.get_by_id(chat.owner_id)
        if owner is None:
            return frozenset()
        plan = await self.get_effective_plan(owner)
        return frozenset(plan.modules or [])

    async def tutor_limits(self, owner: User) -> TutorLimits:
        """Groups and students allowed on the plan this owner is using."""
        plan = await self.get_effective_plan(owner)
        return TutorLimits(
            max_groups=plan.max_tutor_groups,
            max_students=plan.max_tutor_students,
            plan_code=plan.code,
            fees=plan.code != "free",
        )

    async def snapshot(self, owner: User) -> PlanSnapshot:
        """Numbers for the plan screen and the chat card."""
        plan = await self.get_effective_plan(owner)
        sub = await self._subs.get_open(owner.id)
        now = self._now()
        kind = "free"
        days: int | None = None
        if sub is not None and sub.expires_at > now and plan.code != "free":
            kind = "trial" if sub.status == SubscriptionStatus.TRIAL else "active"
            days = _days_left(sub.expires_at, now)
        used, _maximum, _left = await self._quota(owner)
        chats_used = await self._chats.count_active(owner.id)
        return PlanSnapshot(
            plan=plan,
            kind=kind,
            days_left=days,
            chats_used=chats_used,
            ai_used=used,
        )

    async def _quota(self, owner: User) -> tuple[int, int, int]:
        plan = await self.get_effective_plan(owner)
        period = self._now().strftime("%Y-%m")
        used = await self._usage.get_count(owner.id, AI_METRIC, period)
        left = max(0, plan.ai_generations_per_month - used)
        return used, plan.ai_generations_per_month, left

    async def _require_free(self) -> Plan:
        free = await self._plans.get_by_code("free")
        if free is None:
            raise RuntimeError("free plan is not seeded")
        return free


def _days_left(expires_at: datetime, now: datetime) -> int:
    seconds = (expires_at - now).total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)
