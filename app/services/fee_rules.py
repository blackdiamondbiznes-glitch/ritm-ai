"""Pure fee dates and status. No database."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.clock import TASHKENT


def tashkent_today(moment) -> date:
    """Calendar date in Asia/Tashkent."""
    return moment.astimezone(TASHKENT).date()


def on_or_after(start: date, billing_day: int) -> date:
    """First billing day on or after `start`. The day is always 1..28."""
    this = date(start.year, start.month, billing_day)
    if this >= start:
        return this
    return add_month(this)


def add_month(day: date) -> date:
    """Same day next month. Billing days stay inside the month."""
    year, month = day.year, day.month + 1
    if month == 13:
        year, month = year + 1, 1
    return date(year, month, day.day)


def periods_due(billing_day: int, start: date, today: date) -> list[tuple[date, date]]:
    """Monthly periods from the first billing day through the one that contains today."""
    cursor = on_or_after(start, billing_day)
    found: list[tuple[date, date]] = []
    while cursor <= today:
        nxt = add_month(cursor)
        found.append((cursor, nxt - timedelta(days=1)))
        cursor = nxt
    return found


def invoice_status(paid: int, amount: int, due_on: date, today: date, current: str) -> str:
    """Paid wins. A waived invoice stays waived. Otherwise overdue after due_on."""
    if current == "waived":
        return "waived"
    if paid >= amount:
        return "paid"
    if today > due_on:
        return "overdue"
    return "due"
