"""Postgres test helpers."""

from sqlalchemy import text


async def allow_purge(session) -> None:
    """Let this transaction delete append-only history rows (payment_events, audit_logs)."""
    await session.execute(text("SET LOCAL ritm.allow_purge = 'on'"))
