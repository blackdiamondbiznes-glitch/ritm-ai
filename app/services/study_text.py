"""Short Telegram summary of the student cabinet. User text is escaped."""

from __future__ import annotations

from datetime import datetime
from html import escape

from app.i18n import t
from app.services.clock import TASHKENT


def summary(payload: dict, lang: str) -> str:
    """Next lesson and fee for each group, then pending requests."""
    groups = payload.get("groups") or []
    pending = payload.get("pending") or []
    if not groups and not pending:
        return t("learn_empty", lang)
    lines = [t("learn_title", lang)]
    for item in groups:
        lines.append(_line(item, lang))
    for item in pending:
        lines.append(t("learn_pending", lang, name=_safe(item.get("group_name") or "")))
    return "\n".join(lines)


def _line(item: dict, lang: str) -> str:
    group = item.get("group") or {}
    return t(
        "learn_line",
        lang,
        name=_safe(group.get("name") or ""),
        when=_when(item.get("next_session"), lang),
        fee=_fee(item.get("fee"), lang),
    )


def _when(session: dict | None, lang: str) -> str:
    if not session or not session.get("starts_at"):
        return t("learn_no_lesson", lang)
    moment = datetime.fromisoformat(session["starts_at"]).astimezone(TASHKENT)
    return t(
        "learn_when",
        lang,
        day=moment.day,
        month=t(f"learn_m{moment.month}", lang),
        time=moment.strftime("%H:%M"),
    )


def _fee(fee: dict | None, lang: str) -> str:
    if not fee:
        return t("learn_fee_none", lang)
    if fee.get("status") in {"paid", "waived"}:
        return t("learn_paid", lang)
    total = fee.get("lessons_total")
    if total is not None:
        return t("learn_pack", lang, used=fee.get("lessons_used") or 0, total=total)
    amount = fee.get("amount")
    if amount is None:
        return t("learn_fee_none", lang)
    due = fee.get("due_on") or ""
    month = int(due[5:7]) if len(due) >= 7 else 1
    day = int(due[8:10]) if len(due) >= 10 else 1
    return t(
        "learn_due",
        lang,
        amount=_money(int(amount)),
        day=day,
        month=t(f"learn_m{month}", lang),
    )


def _money(amount: int) -> str:
    text = f"{amount:,}".replace(",", " ")
    return f"{text} so'm"


def _safe(value: str) -> str:
    return escape(value).replace("{", "&#123;").replace("}", "&#125;")
