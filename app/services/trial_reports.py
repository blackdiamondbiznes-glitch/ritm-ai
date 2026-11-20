"""Trial engagement numbers and when each report should fire."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.models.chats import Chat
from app.db.models.subscriptions import SubscriptionStatus
from app.db.repositories.chats import ChatRepository
from app.db.repositories.engagement import EngagementRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.clock import Clock, utcnow


def report_offsets(trial_days: int) -> tuple[int, ...]:
    """Three unique day offsets after trial start, when the length allows.

    A 15-day trial fires on days 3, 8 and 13. A 5-day trial fires on 1, 2 and 3.
    The last offset is always the conversion reminder (two days before expiry
    when that day is free, otherwise the latest distinct day).
    """
    days = max(1, trial_days)
    late = max(1, days - 2)
    mid = max(1, (days + 1) // 2)
    early = 3 if days >= 8 else 1
    chosen: list[int] = []
    for offset in (early, mid, late):
        value = min(max(1, offset), days)
        if value not in chosen:
            chosen.append(value)
    for offset in range(1, days + 1):
        if len(chosen) >= 3:
            break
        if offset not in chosen:
            chosen.append(offset)
    return tuple(sorted(chosen))


def late_offset(trial_days: int) -> int:
    """The last report, which includes the plan price and a payment button."""
    offsets = report_offsets(trial_days)
    return offsets[-1]


@dataclass(frozen=True)
class TrialStats:
    """Activity for one chat since the trial began."""

    chat: Chat
    posts: int
    answers: int
    participants: int
    best_day: str | None
    days_left: int
    late: bool


class TrialReportService:
    """Build the numbers for a private trial report."""

    def __init__(
        self,
        engagement: EngagementRepository,
        chats: ChatRepository,
        subscriptions: SubscriptionRepository,
        trial_days: int,
        now: Clock | None = None,
    ) -> None:
        self._engagement = engagement
        self._chats = chats
        self._subs = subscriptions
        self._trial_days = trial_days
        self._now = now or utcnow

    def offsets(self) -> tuple[int, ...]:
        """Day numbers used by the planner."""
        return report_offsets(self._trial_days)

    def is_due(self, started_at: datetime, offset: int, now: datetime | None = None) -> bool:
        """True when `offset` full days have passed since the trial started."""
        moment = now or self._now()
        return moment >= started_at + timedelta(days=offset)

    def is_late(self, offset: int) -> bool:
        """The conversion reminder uses the last planned day."""
        return offset == late_offset(self._trial_days)

    async def stats_for(self, chat: Chat, started_at: datetime, expires_at: datetime) -> TrialStats:
        """Count posts and quiz activity from `started_at` onward."""
        now = self._now()
        posts = await self._engagement.posts_since(chat.id, started_at)
        answers = await self._engagement.answers_since(chat.id, started_at)
        people = await self._engagement.participants_since(chat.id, started_at)
        best = await self._engagement.best_day(chat.id, started_at)
        left = max(0, int((expires_at - now).total_seconds() // 86400))
        late = now >= started_at + timedelta(days=late_offset(self._trial_days))
        day = best.strftime("%d.%m.%Y") if best is not None else None
        return TrialStats(chat, posts, answers, people, day, left, late)

    async def live_report(self, owner_id: int) -> TrialStats | None:
        """Current numbers for the owner's first active chat, if a trial is open."""
        sub = await self._subs.get_open(owner_id)
        if sub is None or sub.status != SubscriptionStatus.TRIAL or sub.expires_at <= self._now():
            return None
        chat = await self.first_chat(owner_id)
        if chat is None:
            return None
        return await self.stats_for(chat, sub.started_at, sub.expires_at)

    async def first_chat(self, owner_id: int) -> Chat | None:
        """The owner's first active chat, used when a report has no chat id."""
        rows = await self._chats.list_active_for_owner(owner_id)
        return rows[0] if rows else None
