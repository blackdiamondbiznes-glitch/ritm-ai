"""A due tutor reminder is queued once, then sent once."""

from datetime import UTC, datetime

import pytest
from app.db.models.jobs import Job, JobStatus
from app.db.models.reminders import TutorReminder
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.jobs.reminder import ReminderHandler
from app.jobs.runner import JobCancel
from app.services.reminders import ReminderError, ReminderService, parse_reminder

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


class _Reminders:
    def __init__(self) -> None:
        self.rows: list[TutorReminder] = []
        self._next = 1

    async def list_for_owner(self, owner_id: int) -> list[TutorReminder]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, reminder_id: int) -> TutorReminder | None:
        for row in self.rows:
            if row.id == reminder_id and row.owner_id == owner_id:
                return row
        return None

    async def get(self, reminder_id: int) -> TutorReminder | None:
        for row in self.rows:
            if row.id == reminder_id:
                return row
        return None

    async def due(self, now: datetime) -> list[TutorReminder]:
        return [row for row in self.rows if row.queued_at is None and row.send_at <= now]

    async def add(self, row: TutorReminder) -> TutorReminder:
        row.id = self._next
        self._next += 1
        self.rows.append(row)
        return row

    async def save(self, row: TutorReminder) -> TutorReminder:
        return row

    async def delete(self, row: TutorReminder) -> None:
        self.rows.remove(row)


class _Students:
    def __init__(self) -> None:
        self.rows = [TutorStudent(id=4, owner_id=1, name="Ali", status="paid", amount_uzs=0)]

    async def list_for_owner(self, owner_id: int) -> list[TutorStudent]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, student_id: int) -> TutorStudent | None:
        for row in self.rows:
            if row.id == student_id and row.owner_id == owner_id:
                return row
        return None


class _Jobs:
    def __init__(self) -> None:
        self.rows: list[Job] = []

    async def add(self, job: Job) -> Job:
        job.id = len(self.rows) + 1
        self.rows.append(job)
        return job


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def _service() -> tuple[ReminderService, _Reminders, _Jobs]:
    reminders = _Reminders()
    jobs = _Jobs()
    return ReminderService(reminders, _Students(), jobs, now=lambda: NOW), reminders, jobs


async def test_due_reminder_is_queued_once() -> None:
    service, reminders, jobs = _service()
    await service.create(
        1, {"text": "  Ali darsi  ", "student_id": 4, "send_at": "2026-11-21T15:00"}
    )
    assert reminders.rows[0].send_at.astimezone(UTC).hour == 10
    assert await service.enqueue_due(NOW) == 1
    assert await service.enqueue_due(NOW) == 0
    assert len(jobs.rows) == 1
    assert jobs.rows[0].type == "tutor_reminder"
    assert jobs.rows[0].payload == {"reminder_id": 1}
    with pytest.raises(ReminderError) as other:
        await service.create(1, {"text": "Sir", "student_id": 9, "send_at": "2026-11-21T16:00"})
    assert other.value.code == "student"


def test_rejects_a_reminder_without_text_or_time() -> None:
    for body in ({}, {"text": "  "}, {"text": "Eslash", "send_at": "ertaga"}):
        with pytest.raises(ReminderError):
            parse_reminder(body)


async def test_handler_sends_once() -> None:
    _service_obj, reminders, jobs = _service()
    row = TutorReminder(
        id=3,
        owner_id=1,
        student_id=None,
        text="Dars boshlandi",
        send_at=NOW,
    )
    reminders.rows.append(row)
    users = type("Users", (), {})()

    async def get_by_id(user_id: int) -> User:
        assert user_id == 1
        return User(id=1, telegram_id=555, full_name="Ali")

    users.get_by_id = get_by_id
    bot = _Bot()
    handler = ReminderHandler(bot, reminders, users, now=lambda: NOW)
    job = Job(
        type="tutor_reminder",
        payload={"reminder_id": 3},
        run_at=NOW,
        status=JobStatus.PENDING,
    )
    await handler.handle(job)
    assert bot.sent == [(555, "Dars boshlandi")]
    assert row.sent_at == NOW
    with pytest.raises(JobCancel):
        await handler.handle(job)
    assert bot.sent == [(555, "Dars boshlandi")]
    assert jobs.rows == []


async def test_handler_escapes_html_in_the_reminder() -> None:
    _service_obj, reminders, _jobs = _service()
    row = TutorReminder(
        id=4,
        owner_id=1,
        student_id=None,
        text="<b> & 2<3",
        send_at=NOW,
    )
    reminders.rows.append(row)
    users = type("Users", (), {})()

    async def get_by_id(user_id: int) -> User:
        assert user_id == 1
        return User(id=1, telegram_id=555, full_name="Ali")

    users.get_by_id = get_by_id
    bot = _Bot()
    handler = ReminderHandler(bot, reminders, users, now=lambda: NOW)
    job = Job(
        type="tutor_reminder",
        payload={"reminder_id": 4},
        run_at=NOW,
        status=JobStatus.PENDING,
    )
    await handler.handle(job)
    assert bot.sent == [(555, "&lt;b&gt; &amp; 2&lt;3")]
