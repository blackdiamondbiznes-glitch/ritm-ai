"""Trial report days, once-only planning, and a single expiry notice."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.db.models.jobs import Job, JobStatus
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.jobs.trial_nudge import EXPIRY, TrialNudgeHandler, TrialNudgePlanner
from app.services.trial_reports import TrialReportService, report_offsets

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)


def test_offsets_match_a_fifteen_day_and_a_five_day_trial() -> None:
    assert report_offsets(15) == (3, 8, 13)
    assert report_offsets(5) == (1, 2, 3)


def _reports(days: int = 5) -> TrialReportService:
    return TrialReportService(
        SimpleNamespace(),
        _Chats(),
        _Subs(),
        days,
        now=lambda: NOW,
    )


async def test_planner_enqueues_each_milestone_once() -> None:
    started = NOW - timedelta(days=2)
    sub = _trial(started, started + timedelta(days=5))
    subs = _Subs([sub])
    chats = _Chats()
    jobs = _Jobs()
    notices = _Notices()
    planner = TrialNudgePlanner(subs, chats, jobs, notices, _reports(5), now=lambda: NOW)
    await planner.enqueue_due()
    kinds = sorted(str((job.payload or {}).get("kind")) for job in jobs.rows)
    assert kinds == ["trial_report:1", "trial_report:2"]
    await planner.enqueue_due()
    assert len(jobs.rows) == 2
    # After the notices exist, a later tick adds nothing new.
    for job in list(jobs.rows):
        await notices.add(1, str((job.payload or {})["kind"]), NOW, chat_id=7)
    await planner.enqueue_due()
    assert len(jobs.rows) == 2


async def test_expiry_notice_is_queued_once_and_handler_sends_once() -> None:
    sub = _trial(NOW - timedelta(days=6), NOW - timedelta(minutes=1))
    subs = _Subs([sub])
    chats = _Chats()
    jobs = _Jobs()
    notices = _Notices()
    reports = _reports(5)
    planner = TrialNudgePlanner(subs, chats, jobs, notices, reports, now=lambda: NOW)
    await planner.enqueue_due()
    await planner.enqueue_due()
    assert [job.type for job in jobs.rows] == [EXPIRY]
    sender = _Sender()
    handler = TrialNudgeHandler(
        _Users(),
        chats,
        subs,
        notices,
        reports,
        sender,  # type: ignore[arg-type]
        SimpleNamespace(),
        now=lambda: NOW,
    )
    await handler.handle(jobs.rows[0])
    await handler.handle(jobs.rows[0])
    assert len(sender.texts) == 1
    assert "tugadi" in sender.texts[0] or "Free" in sender.texts[0]
    assert sub.status == SubscriptionStatus.EXPIRED
    assert await notices.was_sent(1, EXPIRY)


def _trial(started: datetime, expires: datetime) -> Subscription:
    return Subscription(
        id=1,
        owner_id=1,
        plan_id=3,
        status=SubscriptionStatus.TRIAL,
        source=SubscriptionSource.TRIAL,
        started_at=started,
        expires_at=expires,
    )


class _Subs:
    def __init__(self, rows: list[Subscription] | None = None) -> None:
        self.rows = rows or []

    async def list_trials(self) -> list[Subscription]:
        return [row for row in self.rows if row.status == SubscriptionStatus.TRIAL]

    async def get_open(self, owner_id: int) -> Subscription | None:
        open_status = {SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE}
        return next(
            (row for row in self.rows if row.owner_id == owner_id and row.status in open_status),
            None,
        )


class _Chats:
    async def list_active_for_owner(self, owner_id: int):
        return [SimpleNamespace(id=7, title="Nmadr", owner_id=owner_id, is_active=True)]

    async def get_by_id(self, chat_id: int):
        return SimpleNamespace(id=chat_id, title="Nmadr", owner_id=1, is_active=True)


class _Jobs:
    def __init__(self) -> None:
        self.rows: list[Job] = []
        self._seq = 0

    async def has_slot(self, typ: str, slot: str) -> bool:
        return any(
            job.type == typ
            and job.status != JobStatus.CANCELED
            and (job.payload or {}).get("slot") == slot
            for job in self.rows
        )

    async def add(self, job: Job) -> Job:
        self._seq += 1
        job.id = self._seq
        self.rows.append(job)
        return job


class _Notices:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    async def was_sent(
        self, owner_id: int, kind: str, *, chat_id: int | None = None, sent_on=None
    ) -> bool:
        key = (owner_id, chat_id or 0, kind)
        return any(row[:3] == key for row in self.rows)

    async def add(self, owner_id: int, kind: str, sent_at, *, chat_id: int | None = None):
        self.rows.append((owner_id, chat_id or 0, kind, sent_at))
        return SimpleNamespace()


class _Users:
    async def get_by_id(self, user_id: int):
        return SimpleNamespace(id=user_id, telegram_id=5052443384, language_code="uz")


class _Sender:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def post(self, bot, chat_id: int, text: str, markup=None) -> int:
        self.texts.append(text)
        return 1


class _OptedOut(_Users):
    async def get_by_id(self, user_id: int):
        return SimpleNamespace(
            id=user_id,
            telegram_id=5052443384,
            language_code="uz",
            notify_reports=False,
            notify_expiry=False,
        )


def _handler(subs, notices, sender) -> TrialNudgeHandler:
    return TrialNudgeHandler(
        _OptedOut(),
        _Chats(),
        subs,
        notices,
        _reports(5),
        sender,  # type: ignore[arg-type]
        SimpleNamespace(),
        now=lambda: NOW,
    )


async def test_opted_out_report_is_recorded_but_not_sent() -> None:
    started = NOW - timedelta(days=2)
    subs = _Subs([_trial(started, started + timedelta(days=5))])
    notices, sender = _Notices(), _Sender()
    job = Job(
        type="trial_engagement_report",
        payload={"owner_id": 1, "kind": "trial_report:1", "chat_id": 7, "offset": 1},
    )
    await _handler(subs, notices, sender).handle(job)
    assert sender.texts == []
    assert await notices.was_sent(1, "trial_report:1", chat_id=7)


async def test_opted_out_expiry_still_expires_the_trial_silently() -> None:
    sub = _trial(NOW - timedelta(days=6), NOW - timedelta(minutes=1))
    subs, notices, sender = _Subs([sub]), _Notices(), _Sender()
    job = Job(type=EXPIRY, payload={"owner_id": 1, "kind": EXPIRY, "chat_id": None})
    await _handler(subs, notices, sender).handle(job)
    assert sender.texts == []
    assert sub.status == SubscriptionStatus.EXPIRED
    assert await notices.was_sent(1, EXPIRY)
