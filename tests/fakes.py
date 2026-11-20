"""In-memory repositories for service tests. No database required."""

from datetime import UTC, datetime, timedelta

from app.db.models.chats import Chat, ChatType
from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.services.access import AccessService
from app.services.admin import AdminService
from app.services.lifecycle import ChatLifecycleService
from app.services.trial import TrialService

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)


def clock() -> datetime:
    """Frozen clock."""
    return NOW


class FakePlans:
    """Plan lookup."""

    def __init__(self, plans: list[Plan]) -> None:
        self._plans = plans

    async def get_by_code(self, code: str) -> Plan | None:
        return next((plan for plan in self._plans if plan.code == code), None)

    async def get_by_id(self, plan_id: int) -> Plan | None:
        return next((plan for plan in self._plans if plan.id == plan_id), None)

    async def list_active(self) -> list[Plan]:
        return [plan for plan in self._plans if plan.is_active]


class FakeSubs:
    """Open-subscription rules, including the single-open constraint."""

    def __init__(self) -> None:
        self.rows: list[Subscription] = []
        self._seq = 0

    async def get_open(self, owner_id: int) -> Subscription | None:
        open_status = {SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE}
        found = [row for row in self.rows if row.owner_id == owner_id and row.status in open_status]
        return found[0] if found else None

    async def add(self, subscription: Subscription) -> Subscription:
        self._seq += 1
        subscription.id = self._seq
        self.rows.append(subscription)
        return subscription

    async def count_open_trials(self, now: datetime) -> int:
        return sum(
            1
            for row in self.rows
            if row.status == SubscriptionStatus.TRIAL and row.expires_at > now
        )

    async def count_open_paid(self, now: datetime) -> int:
        return sum(
            1
            for row in self.rows
            if row.status == SubscriptionStatus.ACTIVE
            and row.source != SubscriptionSource.TRIAL
            and row.expires_at > now
        )


class FakeChats:
    """Chat rows owned by the test."""

    def __init__(self) -> None:
        self.rows: list[Chat] = []
        self._seq = 0

    async def get_by_id(self, chat_id: int) -> Chat | None:
        return next((row for row in self.rows if row.id == chat_id), None)

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Chat | None:
        return next((row for row in self.rows if row.telegram_chat_id == telegram_chat_id), None)

    async def count_active(self, owner_id: int) -> int:
        return sum(1 for row in self.rows if row.owner_id == owner_id and row.is_active)

    async def list_active_for_owner(self, owner_id: int) -> list[Chat]:
        return [row for row in self.rows if row.owner_id == owner_id and row.is_active]

    async def count_all(self) -> int:
        return len(self.rows)

    async def list_active(self) -> list[Chat]:
        return [row for row in self.rows if row.is_active]

    async def get_by_ids(self, ids: list[int]) -> list[Chat]:
        return [row for row in self.rows if row.id in ids]

    async def add(self, chat: Chat) -> Chat:
        self._seq += 1
        chat.id = self._seq
        self.rows.append(chat)
        return chat


class FakeUsers:
    """User lookup."""

    def __init__(self, users: list[User]) -> None:
        self.users = users

    async def get_by_id(self, user_id: int) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return next((user for user in self.users if user.telegram_id == telegram_id), None)

    async def count(self) -> int:
        return len(self.users)

    async def count_founders(self) -> int:
        return sum(1 for user in self.users if user.is_founder)


class FakeUsage:
    """Monthly counters."""

    def __init__(self, counts: dict[tuple[int, str, str], int] | None = None) -> None:
        self.counts = counts or {}

    async def get_count(self, owner_id: int, metric: str, period_key: str) -> int:
        return self.counts.get((owner_id, metric, period_key), 0)

    async def bump(self, owner_id: int, metric: str, period_key: str) -> int:
        key = (owner_id, metric, period_key)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


class FakeAudit:
    """Captured audit rows."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add(self, **kwargs: object) -> None:
        self.rows.append(kwargs)


def make_plans() -> list[Plan]:
    """The four seeded plans, with the limits from the spec."""
    modules = {
        "free": ["daily_content"],
        "start": ["daily_content", "quiz"],
        "pro": ["daily_content", "quiz", "admin_post_quiz", "leaderboard"],
        "agency": ["daily_content", "quiz", "admin_post_quiz", "leaderboard"],
    }
    limits = {"free": (1, 8), "start": (1, 60), "pro": (5, 300), "agency": (30, 1500)}
    plans = []
    names = {"free": "Free", "start": "Start", "pro": "Pro", "agency": "Ultra"}
    for index, code in enumerate(("free", "start", "pro", "agency"), start=1):
        chats, ai = limits[code]
        plans.append(
            Plan(
                id=index,
                code=code,
                name=names[code],
                price_uzs=0,
                max_chats=chats,
                ai_generations_per_month=ai,
                modules=modules[code],
                is_active=True,
                sort_order=index,
            )
        )
    return plans


def make_user(user_id: int = 1, telegram_id: int = 100) -> User:
    """An owner who has not used the trial."""
    return User(id=user_id, telegram_id=telegram_id, language_code="uz", is_blocked=False)


def make_chat(owner: User, telegram_chat_id: int = -1001, *, consumed: bool = False) -> Chat:
    """An active chat row."""
    return Chat(
        id=telegram_chat_id,
        telegram_chat_id=telegram_chat_id,
        type=ChatType.CHANNEL,
        title="Test",
        owner_id=owner.id,
        is_active=True,
        trial_consumed=consumed,
        admins_can_edit=False,
        added_at=NOW,
    )


class World:
    """Wired services sharing one memory."""

    def __init__(self) -> None:
        self.plans = FakePlans(make_plans())
        self.subs = FakeSubs()
        self.chats = FakeChats()
        self.users = FakeUsers([])
        self.usage = FakeUsage()
        self.audit = FakeAudit()
        self.access = AccessService(
            self.plans, self.subs, self.chats, self.usage, self.users, now=clock
        )
        self.trial = TrialService(self.plans, self.subs, self.audit, trial_days=5, now=clock)
        self.lifecycle = ChatLifecycleService(
            self.chats, self.access, self.trial, self.audit, now=clock
        )
        self.admin = AdminService(
            self.users, self.plans, self.subs, self.chats, self.audit, now=clock
        )

    def add_user(self, user: User) -> User:
        self.users.users.append(user)
        return user

    async def add_sub(
        self,
        owner: User,
        code: str,
        status: SubscriptionStatus,
        *,
        days: int,
        source: SubscriptionSource = SubscriptionSource.ADMIN_GRANT,
    ) -> Subscription:
        plan = await self.plans.get_by_code(code)
        assert plan is not None
        sub = Subscription(
            owner_id=owner.id,
            plan_id=plan.id,
            status=status,
            source=source,
            started_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=days),
        )
        return await self.subs.add(sub)
