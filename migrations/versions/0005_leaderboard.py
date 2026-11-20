"""Weekly leaderboard periods and frozen point totals.

Revision ID: 0005_leaderboard
Revises: 0004_quiz_align
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_leaderboard"
down_revision: str | None = "0004_quiz_align"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create period and entry tables."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop the leaderboard tables."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE leaderboard_periods (
        id SERIAL PRIMARY KEY,
        chat_id INTEGER NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        status VARCHAR(16) NOT NULL,
        announced_at TIMESTAMPTZ,
        telegram_message_id BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE leaderboard_periods
        ADD CONSTRAINT fk_leaderboard_periods_chat_id_chats
        FOREIGN KEY (chat_id) REFERENCES chats (id)
    """,
    """
    ALTER TABLE leaderboard_periods
        ADD CONSTRAINT uq_leaderboard_periods_chat_start
        UNIQUE (chat_id, period_start)
    """,
    """
    ALTER TABLE leaderboard_periods
        ADD CONSTRAINT ck_leaderboard_periods_status
        CHECK (status IN ('open', 'announced'))
    """,
    "CREATE INDEX ix_leaderboard_periods_chat_id ON leaderboard_periods (chat_id)",
    """
    CREATE TABLE leaderboard_entries (
        id SERIAL PRIMARY KEY,
        period_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        points INTEGER NOT NULL,
        correct_count INTEGER NOT NULL,
        total_answers INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE leaderboard_entries
        ADD CONSTRAINT fk_leaderboard_entries_period_id_leaderboard_periods
        FOREIGN KEY (period_id) REFERENCES leaderboard_periods (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE leaderboard_entries
        ADD CONSTRAINT fk_leaderboard_entries_user_id_users
        FOREIGN KEY (user_id) REFERENCES users (id)
    """,
    """
    ALTER TABLE leaderboard_entries
        ADD CONSTRAINT uq_leaderboard_entries_period_user
        UNIQUE (period_id, user_id)
    """,
    "CREATE INDEX ix_leaderboard_entries_period_id ON leaderboard_entries (period_id)",
    "CREATE INDEX ix_leaderboard_entries_user_id ON leaderboard_entries (user_id)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE IF EXISTS leaderboard_entries",
    "DROP TABLE IF EXISTS leaderboard_periods",
)
