"""Choose a widget for a tutor notice and remember the message id."""

from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.widgets.markup import cabinet_markup, study_markup
from app.bot.widgets.send import send_card
from app.db.models.invoices import TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.tutor_notices import TutorNotice
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.topics import TopicRepository
from app.db.repositories.users import UserRepository, teacher_name_of
from app.db.repositories.widget_messages import WidgetMessageRepository
from app.services.attendance import AttendanceService
from app.services.widget_cards import (
    attendance_data,
    digest_data,
    fee_data,
    lesson_data,
)

logger = logging.getLogger(__name__)

_STUDENT = {"lesson": "lesson", "homework": "lesson", "fee_due": "fee", "fee_overdue": "fee"}
_OWNER = {"fee_due": "digest", "attendance": "attendance"}


async def send_notice(
    bot: Bot,
    session: AsyncSession,
    notice: TutorNotice,
    *,
    chat_id: int,
    lang: str,
    caption: str,
    enabled: bool,
    params: dict | None = None,
) -> bool:
    """Send a private-chat card. False means the caller should send the caption."""
    kind = _kind_for(notice)
    if kind is None:
        return False
    data = await _state(session, notice, lang, kind, params)
    if data is None:
        return False
    markup = cabinet_markup(lang) if notice.target == "owner" else study_markup(lang)
    queries = kind in {"lesson", "fee", "attendance"}
    message = await send_card(
        bot,
        chat_id=chat_id,
        kind=kind,
        data=data,
        caption=caption,
        markup=markup,
        allow_queries=queries,
        enabled=enabled,
    )
    await _remember(session, kind, notice, chat_id, message)
    return True


async def remember(session: AsyncSession, kind: str, ref_id: int, message: Message | None) -> None:
    """Keep a sent widget so a later edit can find it."""
    if message is None or getattr(message, "message_id", None) is None:
        return
    chat = getattr(message, "chat", None)
    telegram_id = getattr(chat, "id", None)
    if telegram_id is None:
        return
    await WidgetMessageRepository(session).remember(
        kind, ref_id, int(telegram_id), message.message_id
    )


async def edit_card(bot: Bot, session: AsyncSession, kind: str, ref_id: int, data: dict) -> None:
    """Push new chat_data to every stored message of this card."""
    from app.bot.widgets.send import clip_data

    payload = clip_data(data)
    for row in await WidgetMessageRepository(session).find(kind, ref_id):
        try:
            await bot.edit_message_widget_data(
                chat_id=row.telegram_id, message_id=row.message_id, chat_data=payload
            )
        except (TelegramAPIError, OSError, AttributeError):
            logger.info("widget edit skipped kind=%s ref=%s", kind, ref_id)


def _kind_for(notice: TutorNotice) -> str | None:
    if notice.target == "student":
        return _STUDENT.get(notice.kind)
    if notice.target == "owner":
        if notice.kind == "attendance":
            return "attendance"
        if notice.kind == "fee_due":
            return "digest"
    return None


async def _state(
    session: AsyncSession, notice: TutorNotice, lang: str, kind: str, params: dict | None
) -> dict | None:
    if kind == "fee":
        invoice = await session.get(TutorInvoice, notice.ref_id)
        if invoice is None:
            return None
        name = await _group_name(session, invoice.group_id)
        return fee_data(lang, name, invoice)
    if kind == "digest":
        data = params or {}
        return digest_data(lang, int(data.get("soon") or 0), int(data.get("late") or 0))
    if kind == "attendance":
        lesson = await session.get(TutorLesson, notice.ref_id)
        if lesson is None or lesson.owner_id is None:
            return None
        marks = AttendanceRepository(session)
        lessons = LessonRepository(session)
        groups = GroupRepository(session)
        sheet = await AttendanceService(marks, lessons, groups).sheet(lesson.owner_id, lesson.id)
        return attendance_data(lang, sheet)
    if kind == "lesson":
        return await _lesson_state(session, notice, lang)
    return None


async def _lesson_state(session: AsyncSession, notice: TutorNotice, lang: str) -> dict | None:
    teacher = ""
    group_name = ""
    starts = None
    homework = ""
    due = None
    if notice.kind == "homework":
        topic = await TopicRepository(session).get(notice.ref_id)
        if topic is None:
            return None
        homework = topic.homework or ""
        due = topic.homework_due
        group_name, teacher = await _group_teacher(session, topic.group_id)
    else:
        lesson = await session.get(TutorLesson, notice.ref_id)
        if lesson is None:
            return None
        starts = lesson.starts_at
        group_name, teacher = await _group_teacher(session, lesson.group_id)
        homework, due = await _homework(session, lesson.group_id)
    return lesson_data(lang, group_name, teacher, starts, homework, due)


async def _group_teacher(session: AsyncSession, group_id: int | None) -> tuple[str, str]:
    if not group_id:
        return "", ""
    group = await GroupRepository(session).get(group_id)
    if group is None:
        return "", ""
    owner = await UserRepository(session).get_by_id(group.owner_id)
    return group.name, teacher_name_of(owner) or ""


async def _group_name(session: AsyncSession, group_id: int | None) -> str:
    if not group_id:
        return ""
    group = await GroupRepository(session).get(group_id)
    return group.name if group is not None else ""


async def _homework(session: AsyncSession, group_id: int | None) -> tuple[str, object]:
    if not group_id:
        return "", None
    topics = await TopicRepository(session).list_for_groups([group_id])
    rows = [row for row in topics if row.homework]
    if not rows:
        return "", None
    rows.sort(key=lambda row: (row.homework_due or date.min, row.id), reverse=True)
    topic = rows[0]
    return topic.homework or "", topic.homework_due


async def _remember(
    session: AsyncSession, kind: str, notice: TutorNotice, chat_id: int, message: Message | None
) -> None:
    if message is None or getattr(message, "message_id", None) is None:
        return
    await WidgetMessageRepository(session).remember(
        kind, notice.ref_id, chat_id, message.message_id
    )
