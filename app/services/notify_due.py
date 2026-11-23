"""Find lesson, fee, and scheduled reminders that are due, and queue each once."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models.groups import TutorGroup
from app.db.repositories.chats import ChatRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.db.repositories.users import UserRepository
from app.services.clock import TASHKENT
from app.services.notify_attendance import enqueue_attendance
from app.services.notify_homework import enqueue_homework
from app.services.notify_queue import deliver
from app.services.notify_rules import day_ref, language, lesson_label, run_at
from app.services.notify_targets import audience, group_dest, student_dest


class NoticePlanner:
    """Queue automatic notices. Sending happens later, in the job handler."""

    def __init__(
        self,
        notes: TutorNoticeRepository,
        groups: GroupRepository,
        chats: ChatRepository,
        jobs: JobRepository,
        users: UserRepository,
        students: StudentRepository,
        reminders: ReminderRepository,
        topics: TopicRepository | None = None,
    ) -> None:
        self._notes = notes
        self._groups = groups
        self._chats = chats
        self._jobs = jobs
        self._users = users
        self._students = students
        self._reminders = reminders
        self._topics = topics

    async def enqueue(self, now: datetime) -> int:
        """Queue everything that became due. A second call adds nothing."""
        lessons = await self._lessons(now)
        fees = await self._fees(now)
        manuals = await self._manual(now)
        home = await enqueue_homework(self, self._topics, now) if self._topics else 0
        roll = await enqueue_attendance(self, now)
        return lessons + fees + manuals + home + roll

    async def _lessons(self, now: datetime) -> int:
        made = 0
        until = now + timedelta(minutes=120)
        for lesson, group in await self._notes.lessons_soon(now, until):
            minutes = int(group.remind_lesson_min or 0)
            if lesson.starts_at is None or now < lesson.starts_at - timedelta(minutes=minutes):
                continue
            when, late = run_at(now, lesson.starts_at, "lesson")
            clock = lesson.starts_at.astimezone(TASHKENT).strftime("%H:%M")
            params = {
                "gap_min": minutes,
                "title": lesson_label(group.name, group.level),
                "time": clock,
                "starts_at": lesson.starts_at.isoformat(),
            }
            if lesson.meeting_url:
                params["meeting_url"] = lesson.meeting_url
            for dest in await audience(self._groups, self._chats, self._users, group):
                if await deliver(
                    self._notes,
                    self._jobs,
                    kind="lesson",
                    ref=lesson.id,
                    target=dest["target"],
                    target_id=dest["target_id"],
                    telegram_id=dest["telegram_id"],
                    lang=dest["lang"],
                    template="notify_lesson",
                    params=params,
                    quota=True,
                    owner_id=group.owner_id,
                    run_at=when,
                    skip=late,
                ):
                    made += 1
        return made

    async def _fees(self, now: datetime) -> int:
        today = now.astimezone(TASHKENT).date()
        groups = await self._notes.fee_groups()
        invoices = await self._notes.open_invoices([group.id for group in groups])
        by_group = {group.id: group for group in groups}
        counts: dict[int, list[int]] = {}
        made = 0
        warned: set[int] = set()
        for invoice in invoices:
            group = by_group.get(invoice.group_id)
            if group is None or group.remind_fee_days is None:
                continue
            kind = _fee_kind(today, invoice.due_on, int(group.remind_fee_days))
            if kind is None:
                continue
            bucket = counts.setdefault(group.owner_id, [0, 0])
            bucket[0 if kind == "fee_due" else 1] += 1
            made += await self._fee_student(group, invoice, kind, now)
            if group.id not in warned:
                warned.add(group.id)
                made += await self._fee_group(group, today, now)
        for owner_id, (soon, late) in counts.items():
            made += await self._digest(owner_id, today, soon, late, now)
        return made

    async def _fee_student(self, group: TutorGroup, invoice, kind: str, now: datetime) -> int:
        members = {row.id: row for row in await self._groups.members(group.id)}
        student = members.get(invoice.student_id)
        if student is None:
            return 0
        dest = await student_dest(self._users, student)
        if dest is None:
            return 0
        when, _late = run_at(now, None, kind)
        queued = await deliver(
            self._notes,
            self._jobs,
            kind=kind,
            ref=invoice.id,
            target="student",
            target_id=dest["target_id"],
            telegram_id=dest["telegram_id"],
            lang=dest["lang"],
            template="notify_fee_student",
            params={
                "title": lesson_label(group.name, group.level),
                "amount": str(invoice.amount_uzs),
                "date": invoice.due_on.isoformat(),
            },
            quota=True,
            owner_id=group.owner_id,
            run_at=when,
        )
        return 1 if queued else 0

    async def _fee_group(self, group: TutorGroup, today, now: datetime) -> int:
        """One generic line per linked chat per day, and only when the teacher asked."""
        if not group.fee_in_group:
            return 0
        dest = await group_dest(self._chats, self._users, group)
        if dest is None:
            return 0
        when, _late = run_at(now, None, "fee_due")
        queued = await deliver(
            self._notes,
            self._jobs,
            kind="fee_due",
            ref=day_ref(today),
            target="group",
            target_id=dest["target_id"],
            telegram_id=dest["telegram_id"],
            lang=dest["lang"],
            template="notify_fee_group",
            params={},
            quota=True,
            owner_id=group.owner_id,
            run_at=when,
        )
        return 1 if queued else 0

    async def _digest(self, owner_id: int, today, soon: int, late: int, now: datetime) -> int:
        owner = await self._users.get_by_id(owner_id)
        if owner is None:
            return 0
        when, _late = run_at(now, None, "fee_due")
        queued = await deliver(
            self._notes,
            self._jobs,
            kind="fee_due",
            ref=day_ref(today),
            target="owner",
            target_id=owner.id,
            telegram_id=owner.telegram_id,
            lang=language(owner.language_code),
            template="notify_fee_digest",
            params={"soon": soon, "late": late},
            quota=False,
            owner_id=owner.id,
            run_at=when,
        )
        return 1 if queued else 0

    async def _manual(self, now: datetime) -> int:
        made = 0
        for row in await self._reminders.due_for(now, ("student", "group")):
            made += await self._one_manual(row, now)
            row.queued_at = now
            await self._reminders.save(row)
        return made

    async def _one_manual(self, row, now: datetime) -> int:
        when, _late = run_at(now, None, "manual")
        params = {"text": row.text}
        if row.audience == "student" and row.student_id is not None:
            student = await self._students.get_owned(row.owner_id, row.student_id)
            dest = await student_dest(self._users, student) if student is not None else None
            if dest is None:
                return 0
            queued = await deliver(
                self._notes,
                self._jobs,
                kind="manual",
                ref=row.id,
                target="student",
                target_id=dest["target_id"],
                telegram_id=dest["telegram_id"],
                lang=dest["lang"],
                template="notify_text",
                params=params,
                quota=True,
                owner_id=row.owner_id,
                run_at=when,
            )
            return 1 if queued else 0
        if row.audience == "group" and row.group_id is not None:
            group = await self._groups.get_owned(row.owner_id, row.group_id)
            dest = await group_dest(self._chats, self._users, group) if group is not None else None
            if dest is None:
                return 0
            queued = await deliver(
                self._notes,
                self._jobs,
                kind="manual",
                ref=row.id,
                target="group",
                target_id=dest["target_id"],
                telegram_id=dest["telegram_id"],
                lang=dest["lang"],
                template="notify_text",
                params=params,
                quota=True,
                owner_id=row.owner_id,
                run_at=when,
            )
            return 1 if queued else 0
        return 0


def _fee_kind(today, due_on, days: int) -> str | None:
    if due_on - timedelta(days=days) == today:
        return "fee_due"
    if due_on + timedelta(days=1) == today:
        return "fee_overdue"
    return None
