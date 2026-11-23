"""The private monthly message. Group names are escaped."""

from __future__ import annotations

from html import escape

from app.i18n import t


def render_report(data: dict, lang: str) -> str:
    """One message: each group, then how many students joined or left."""
    lines = [t("report_title", lang, month=escape(str(data.get("month") or "")))]
    for group in data.get("groups") or []:
        rate = group.get("attendance_rate")
        shown = "—" if rate is None else f"{round(rate * 100)}%"
        lines.append(
            t(
                "report_group",
                lang,
                name=escape(str(group.get("name") or "")),
                rate=shown,
                collected=_money(int(group.get("collected_uzs") or 0)),
                outstanding=_money(int(group.get("outstanding_uzs") or 0)),
            )
        )
    lines.append(
        t(
            "report_people",
            lang,
            new=int(data.get("new_students") or 0),
            left=int(data.get("left_students") or 0),
        )
    )
    return "\n".join(lines)


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"
