"""Answer private-chat widget taps. Always reply within 15 seconds."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import WidgetQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.enroll_notice import decision_text, tell
from app.bot.widgets.send import clip_data
from app.db.models.invoices import TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.widget_messages import WidgetMessageRepository
from app.services.attendance import AttendanceError, AttendanceService
from app.services.enrollment import EnrollmentError, EnrollmentService
from app.services.fee_usage import PackageUsage
from app.services.fees import FeeService
from app.services.widget_cards import attendance_data, enroll_data, fee_data

logger = logging.getLogger(__name__)
router = Router(name="widget_queries")

_ROLL = {"p": "present", "l": "late", "a": "absent", "e": "excused"}


@router.widget_query()
async def on_widget_query(
    query: WidgetQuery,
    current_user: User,
    session: AsyncSession,
    enrollment: EnrollmentService,
) -> None:
    """Validate the tap, mutate state, then answer and edit the card."""
    if query.chat is None or query.message_id is None or query.chat.type != "private":
        await query.answer(data="denied")
        return
    stored = await WidgetMessageRepository(session).by_message(query.chat.id, query.message_id)
    if stored is None or stored.telegram_id != query.from_user.id:
        await query.answer(data="denied")
        return
    try:
        payload = await _handle(
            query.bot, query, current_user, session, enrollment, stored.kind, stored.ref_id
        )
    except (AttendanceError, EnrollmentError) as exc:
        logger.info("widget query rejected code=%s", getattr(exc, "code", exc))
        await query.answer(data=str(getattr(exc, "code", "error")))
        return
    except Exception:
        logger.exception("widget query failed kind=%s", stored.kind)
        await query.answer(data="error")
        return
    await query.answer()
    if payload.startswith("{"):
        try:
            await query.bot.edit_message_widget_data(
                chat_id=query.chat.id, message_id=query.message_id, chat_data=payload
            )
        except Exception:
            logger.info("widget query edit skipped kind=%s", stored.kind)


async def _handle(
    bot: Bot,
    query: WidgetQuery,
    user: User,
    session: AsyncSession,
    enrollment: EnrollmentService,
    kind: str,
    ref_id: int,
) -> str:
    code = (query.data or "")[:64]
    lang = user.language_code or "uz"
    if kind == "fee" and code == "r":
        invoice = await session.get(TutorInvoice, ref_id)
        if invoice is None:
            return "missing"
        group = await GroupRepository(session).get(invoice.group_id)
        name = group.name if group is not None else ""
        return clip_data(fee_data(lang, name, invoice))
    if kind == "attendance":
        return await _roll(session, user, ref_id, code)
    if kind == "enroll":
        return await _decide(bot, session, user, enrollment, ref_id, code)
    return "ok"


async def _roll(session: AsyncSession, user: User, lesson_id: int, code: str) -> str:
    lesson = await session.get(TutorLesson, lesson_id)
    if lesson is None:
        raise AttendanceError("missing")
    owner = await UserRepository(session).get_by_id(lesson.owner_id)
    if owner is None or owner.telegram_id != user.telegram_id:
        raise AttendanceError("missing")
    action, _, student_raw = code.partition(":")
    service = _attendance(session)
    student_id = int(student_raw) if student_raw.isdigit() else 0
    if action in _ROLL:
        if student_id <= 0:
            raise AttendanceError("student")
        await service.save(
            owner.id, lesson.id, {"marks": [{"student_id": student_id, "status": _ROLL[action]}]}
        )
        focus = None
    elif action == "b":
        focus = _previous_id(await service.sheet(owner.id, lesson.id), student_id)
    else:
        raise AttendanceError("choice")
    sheet = await service.sheet(owner.id, lesson.id)
    lang = user.language_code or "uz"
    return clip_data(attendance_data(lang, sheet, focus))


def _previous_id(sheet: dict, student_id: int) -> int | None:
    ids = [int(row["student_id"]) for row in sheet.get("students") or []]
    if student_id in ids:
        return ids[max(ids.index(student_id) - 1, 0)]
    return ids[0] if ids else None


def _attendance(session: AsyncSession) -> AttendanceService:
    invoices = InvoiceRepository(session)
    groups = GroupRepository(session)
    fees = FeeService(invoices, groups, UserRepository(session))
    return AttendanceService(
        AttendanceRepository(session),
        LessonRepository(session),
        groups,
        fees=PackageUsage(invoices, groups, fees),
    )


async def _decide(
    bot: Bot,
    session: AsyncSession,
    user: User,
    enrollment: EnrollmentService,
    ref_id: int,
    code: str,
) -> str:
    group_id, student_id = ref_id >> 32, ref_id & 0xFFFFFFFF
    pupil = await session.get(TutorStudent, student_id)
    name = pupil.name if pupil is not None else ""
    if code == "y":
        result = await enrollment.approve(user.id, group_id, student_id)
        status = "yes"
        key = "enroll_yes"
    elif code == "n":
        result = await enrollment.reject(user.id, group_id, student_id)
        status = "no"
        key = "enroll_no"
    else:
        raise EnrollmentError("missing")
    telegram_id = result.get("telegram_id")
    if isinstance(telegram_id, int):
        pupil = await UserRepository(session).get_by_telegram_id(telegram_id)
        lang = pupil.language_code if pupil is not None else "uz"
        await tell(bot, telegram_id, decision_text(lang, key, result["group"]))
    lang = user.language_code or "uz"
    return clip_data(enroll_data(lang, name, result["group"], group_id, student_id, status))
