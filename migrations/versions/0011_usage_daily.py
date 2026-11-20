"""Daily usage counters and one index for the M4 charts.

usage_counters only keeps one row per owner and month, so a per-day chart has no
source data. usage_daily is written next to it from now on; older days stay
available only as monthly totals.

ix_quiz_answers_quiz_answered: chart queries reach answers through the chat's
quizzes (quiz_id) and keep only a date window. With only (quiz_id) every probe
read all of a quiz's answers from the heap. On a 1.17M-answer test set
(200 chats, 2 quizzes a day for a year), EXPLAIN ANALYZE for a 5-chat, 7-day
window went from 43.8k to 14.6k shared buffers and from ~35-48 ms to ~13-15 ms
(index-only scan on quiz_id + answered_at, user_id and is_correct included).

Revision ID: 0011_usage_daily
Revises: 0010_payment_trust
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_usage_daily"
down_revision: str | None = "0010_payment_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create usage_daily."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop usage_daily."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE usage_daily (
        owner_id INTEGER NOT NULL,
        metric VARCHAR(32) NOT NULL,
        day DATE NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT pk_usage_daily PRIMARY KEY (owner_id, metric, day),
        CONSTRAINT fk_usage_daily_owner_id_users FOREIGN KEY (owner_id) REFERENCES users (id)
    )
    """,
    "CREATE INDEX ix_usage_daily_day ON usage_daily (day)",
    "CREATE INDEX ix_quiz_answers_quiz_answered ON quiz_answers (quiz_id, answered_at)"
    " INCLUDE (user_id, is_correct)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_quiz_answers_quiz_answered",
    "DROP TABLE IF EXISTS usage_daily",
)
