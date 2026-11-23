"""Compact chat_data dicts and captions for private-chat widgets."""

from __future__ import annotations

from datetime import date, datetime

from app.i18n import t
from app.services.clock import TASHKENT

_NAME = 40
_HW = 200


def clip(value: object, limit: int = _NAME) -> str:
    """Shorten a name or line so the 1024-byte state stays in budget."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def clock(value: datetime | str | None) -> str:
    """Tashkent day and 24-hour time, or empty."""
    moment = _when(value)
    if moment is None:
        return ""
    return moment.astimezone(TASHKENT).strftime("%d.%m %H:%M")


def day(value: date | datetime | str | None) -> str:
    """Tashkent date as dd.mm.yyyy."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.astimezone(TASHKENT).strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    raw = str(value)
    if len(raw) >= 10 and raw[4] == "-":
        return f"{raw[8:10]}.{raw[5:7]}.{raw[:4]}"
    return raw


def lesson_data(
    lang: str,
    group: str,
    teacher: str,
    starts_at: datetime | str | None,
    homework: str,
    due: date | str | None,
) -> dict:
    """Student lesson and homework card."""
    return {
        "l": lang,
        "g": clip(group),
        "w": clip(teacher),
        "when": clock(starts_at),
        "hw": clip(homework, _HW),
        "due": day(due),
    }


def fee_data(lang: str, group: str, invoice) -> dict:
    """Student fee card from an invoice row or a mapping."""
    if isinstance(invoice, dict):
        status = invoice.get("status") or "due"
        amount = int(invoice.get("amount_uzs") or invoice.get("amt") or 0)
        paid = int(invoice.get("paid_uzs") or invoice.get("paid") or 0)
        due = invoice.get("due_on") or invoice.get("due")
        ident = int(invoice.get("id") or invoice.get("inv") or 0)
    else:
        status = invoice.status
        amount = int(invoice.amount_uzs)
        paid = int(invoice.paid_uzs)
        due = invoice.due_on
        ident = int(invoice.id)
    if status == "waived":
        status = "paid"
    return {
        "l": lang,
        "g": clip(group),
        "st": status,
        "amt": amount,
        "paid": paid,
        "due": day(due),
        "inv": ident,
    }


def attendance_data(lang: str, sheet: dict, focus_id: int | None = None) -> dict:
    """One student at a time from an attendance sheet."""
    students = list(sheet.get("students") or [])
    marked = sum(1 for row in students if row.get("status"))
    current = None
    if focus_id:
        current = next(
            (row for row in students if int(row.get("student_id") or 0) == focus_id), None
        )
    if current is None:
        current = next((row for row in students if not row.get("status")), None)
    return {
        "l": lang,
        "g": clip(sheet.get("group_name") or sheet.get("title") or ""),
        "when": clock(sheet.get("starts_at")),
        "lid": int(sheet.get("lesson_id") or 0),
        "n": len(students),
        "done": marked,
        "sid": int(current["student_id"]) if current else 0,
        "name": clip(current.get("name")) if current else "",
    }


def enroll_data(
    lang: str, name: str, group: str, group_id: int, student_id: int, status: str = ""
) -> dict:
    """Teacher join-request card."""
    return {
        "l": lang,
        "name": clip(name),
        "g": clip(group),
        "gid": group_id,
        "sid": student_id,
        "st": status,
    }


def plan_data(lang: str, snap, expiry: str) -> dict:
    """Plan usage bars. `snap` is a PlanSnapshot."""
    name = clip(getattr(snap.plan, "name", ""))
    if snap.kind == "trial":
        title = t("plan_trial", lang, name=name)
    elif snap.kind == "active":
        title = t("plan_active", lang, name=name)
    else:
        title = t("plan_free", lang, name=name)
    return {
        "l": lang,
        "plan": clip(title, 60),
        "exp": expiry,
        "cu": int(snap.chats_used),
        "cm": int(snap.plan.max_chats),
        "au": int(snap.ai_used),
        "am": int(snap.plan.ai_generations_per_month),
    }


def report_data(lang: str, payload: dict) -> dict:
    """Monthly teacher report. Groups are trimmed to fit."""
    groups = []
    for row in payload.get("groups") or []:
        rate = row.get("attendance_rate")
        groups.append(
            {
                "n": clip(row.get("name"), 24),
                "r": "—" if rate is None else f"{round(rate * 100)}%",
                "c": int(row.get("collected_uzs") or 0),
                "o": int(row.get("outstanding_uzs") or 0),
            }
        )
    return {
        "l": lang,
        "m": str(payload.get("month") or ""),
        "groups": groups[:8],
        "new": int(payload.get("new_students") or 0),
        "left": int(payload.get("left_students") or 0),
    }


def digest_data(lang: str, soon: int, late: int) -> dict:
    """Teacher fee totals for today."""
    return {"l": lang, "soon": int(soon), "late": int(late)}


def _when(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def enroll_ref(group_id: int, student_id: int) -> int:
    """Pack group and student ids into the widget ref."""
    return (int(group_id) << 32) | int(student_id)
