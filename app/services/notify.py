"""Teacher settings for notices, plus cancel, move, and announcement queueing."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lessons import TutorLesson
from app.db.repositories.chats import ChatRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.db.repositories.users import UserRepository
from app.services.clock import TASHKENT, utcnow
from app.services.notify_due import NoticePlanner
from app.services.notify_queue import deliver
from app.services.notify_rules import FEE_DAYS, LESSON_MINUTES, lesson_label, move_ref, run_at
from app.services.notify_targets import audience, linked_chat

TEXT_MAX = 1000


class NotifyError(Exception):
    """Invalid notice input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NotifyService:
    """Link a chat, store rules, and queue messages. Nothing is sent here."""

    def __init__(
        self,
        notes: TutorNoticeRepository,
        groups: GroupRepository,
        chats: ChatRepository,
        jobs: JobRepository,
        users: UserRepository,
        students: StudentRepository,
        reminders: ReminderRepository,
        now=utcnow,
    ) -> None:
        self._notes = notes
        self._groups = groups
        self._chats = chats
        self._jobs = jobs
        self._users = users
        self._students = students
        self._reminders = reminders
        self._now = now
        self._planner = NoticePlanner(notes, groups, chats, jobs, users, students, reminders)

    async def enqueue_due(self, now: datetime | None = None) -> int:
        """Queue lesson, fee, and scheduled student or group reminders."""
        return await self._planner.enqueue(now or self._now())

    async def read(self, owner_id: int, group_id: int) -> dict:
        """Rules for this group and the chats the teacher can link."""
        group = await self._owned(owner_id, group_id)
        chats = await self._chats.list_active_for_owner(owner_id)
        return {
            "chat_id": group.chat_id,
            "remind_lesson_min": group.remind_lesson_min,
            "remind_fee_days": group.remind_fee_days,
            "fee_in_group": bool(group.fee_in_group),
            "chats": [{"id": chat.id, "title": chat.title} for chat in chats],
        }

    async def save_rules(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Store the reminder switches. Null turns a reminder off."""
        group = await self._owned(owner_id, group_id)
        if not {"remind_lesson_min", "remind_fee_days", "fee_in_group"} <= set(body):
            raise NotifyError("choice")
        group.remind_lesson_min = _choice(body.get("remind_lesson_min"), LESSON_MINUTES)
        group.remind_fee_days = _choice(body.get("remind_fee_days"), FEE_DAYS)
        flag = body.get("fee_in_group")
        if not isinstance(flag, bool):
            raise NotifyError("choice")
        group.fee_in_group = flag
        await self._groups.save(group)
        return await self.read(owner_id, group_id)

    async def link_chat(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Attach an active chat of this owner, or clear it with null."""
        group = await self._owned(owner_id, group_id)
        if "chat_id" not in body:
            raise NotifyError("chat")
        raw = body.get("chat_id")
        if raw is None:
            group.chat_id = None
        else:
            group.chat_id = await self._chat(owner_id, raw)
        await self._groups.save(group)
        return await self.read(owner_id, group_id)

    async def announce(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Queue one announcement. The tick sends it."""
        group = await self._owned(owner_id, group_id)
        text = _text(body.get("text"))
        to_chat, to_students = _flag(body, "to_chat"), _flag(body, "to_students")
        if not to_chat and not to_students:
            raise NotifyError("target")
        if to_chat and await self._linked(group) is None:
            raise NotifyError("chat")
        ref = int(self._now().timestamp() * 1000) * 100_000 + secrets.randbelow(100_000)
        queued = await self._announce_to(group, text, ref, to_chat, to_students)
        if queued == 0:
            raise NotifyError("target")
        return {"queued": queued}

    async def queue_session(self, owner_id: int, lesson: TutorLesson, kind: str) -> None:
        """Queue cancel or move for a group session. An individual lesson is silent."""
        if lesson.group_id is None or kind not in {"cancel", "move"} or lesson.starts_at is None:
            return
        group = await self._groups.get_owned(owner_id, lesson.group_id)
        if group is None:
            return
        ref = lesson.id if kind == "cancel" else move_ref(lesson.id, lesson.starts_at)
        when, _late = run_at(self._now(), None, kind)
        params = {"title": lesson_label(group.name, group.level), "time": _clock(lesson)}
        template = "notify_cancel" if kind == "cancel" else "notify_move"
        for dest in await audience(self._groups, self._chats, self._users, group):
            await deliver(
                self._notes,
                self._jobs,
                kind=kind,
                ref=ref,
                target=dest["target"],
                target_id=dest["target_id"],
                telegram_id=dest["telegram_id"],
                lang=dest["lang"],
                template=template,
                params=params,
                quota=True,
                owner_id=group.owner_id,
                run_at=when,
            )

    async def _announce_to(
        self, group, text: str, ref: int, to_chat: bool, to_students: bool
    ) -> int:
        when, _late = run_at(self._now(), None, "announce")
        queued = 0
        for dest in await audience(self._groups, self._chats, self._users, group):
            if dest["target"] == "group" and not to_chat:
                continue
            if dest["target"] == "student" and not to_students:
                continue
            if await deliver(
                self._notes,
                self._jobs,
                kind="announce",
                ref=ref,
                target=dest["target"],
                target_id=dest["target_id"],
                telegram_id=dest["telegram_id"],
                lang=dest["lang"],
                template="notify_text",
                params={"text": text},
                quota=True,
                owner_id=group.owner_id,
                run_at=when,
            ):
                queued += 1
        return queued

    async def _owned(self, owner_id: int, group_id: int):
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise NotifyError("missing")
        return group

    async def _chat(self, owner_id: int, raw: object) -> int:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise NotifyError("chat")
        chat = await self._chats.get_by_id(raw)
        if chat is None or chat.owner_id != owner_id or not chat.is_active:
            raise NotifyError("chat")
        return chat.id

    async def _linked(self, group):
        return await linked_chat(self._chats, group)


def notify_for(session: AsyncSession, now=utcnow) -> NotifyService:
    """Build the service on one database session."""
    return NotifyService(
        TutorNoticeRepository(session),
        GroupRepository(session),
        ChatRepository(session),
        JobRepository(session),
        UserRepository(session),
        StudentRepository(session),
        ReminderRepository(session),
        now=now,
    )


def _choice(value: object, allowed: frozenset[int]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
        raise NotifyError("choice")
    return value


def _flag(body: dict, key: str) -> bool:
    if key not in body:
        return False
    value = body.get(key)
    if not isinstance(value, bool):
        raise NotifyError("target")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise NotifyError("empty")
    text = value.strip()
    if not text:
        raise NotifyError("empty")
    if len(text) > TEXT_MAX:
        raise NotifyError("long")
    return text


def _clock(lesson: TutorLesson) -> str:
    assert lesson.starts_at is not None
    return lesson.starts_at.astimezone(TASHKENT).strftime("%H:%M")
