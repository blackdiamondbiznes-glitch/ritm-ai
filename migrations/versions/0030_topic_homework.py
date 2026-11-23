"""Homework on a topic, and the homework notice kind.

Revision ID: 0030_topic_homework
Revises: 0029_tutor_notify
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_topic_homework"
down_revision: str | None = "0029_tutor_notify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = "'lesson', 'fee_due', 'fee_overdue', 'cancel', 'move', 'announce', 'manual', 'homework'"
_OLD = "'lesson', 'fee_due', 'fee_overdue', 'cancel', 'move', 'announce', 'manual'"


def upgrade() -> None:
    """Store homework text and allow the homework delivery kind."""
    op.execute(
        """
        ALTER TABLE tutor_topics
            ADD COLUMN homework TEXT,
            ADD COLUMN homework_due DATE
        """
    )
    op.execute(
        """
        ALTER TABLE tutor_topics
            ADD CONSTRAINT ck_tutor_topics_homework
            CHECK (homework IS NULL OR char_length(homework) <= 1000)
        """
    )
    op.execute("ALTER TABLE tutor_notifications DROP CONSTRAINT ck_tutor_notifications_kind")
    op.execute(
        f"""
        ALTER TABLE tutor_notifications
            ADD CONSTRAINT ck_tutor_notifications_kind CHECK (kind IN ({_KINDS}))
        """
    )


def downgrade() -> None:
    """Remove homework text and the homework delivery kind."""
    op.execute("DELETE FROM tutor_notifications WHERE kind = 'homework'")
    op.execute("ALTER TABLE tutor_notifications DROP CONSTRAINT ck_tutor_notifications_kind")
    op.execute(
        f"""
        ALTER TABLE tutor_notifications
            ADD CONSTRAINT ck_tutor_notifications_kind CHECK (kind IN ({_OLD}))
        """
    )
    op.execute("ALTER TABLE tutor_topics DROP CONSTRAINT ck_tutor_topics_homework")
    op.execute("ALTER TABLE tutor_topics DROP COLUMN homework_due, DROP COLUMN homework")
