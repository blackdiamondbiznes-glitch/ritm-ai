"""Tutor reminders queued once and sent in private chat.

Revision ID: 0017_tutor_reminders
Revises: 0016_cabinet_niche
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_tutor_reminders"
down_revision: str | None = "0016_cabinet_niche"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE tutor_reminders (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        student_id INTEGER,
        text TEXT NOT NULL,
        send_at TIMESTAMPTZ NOT NULL,
        queued_at TIMESTAMPTZ,
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE tutor_reminders
        ADD CONSTRAINT fk_tutor_reminders_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_reminders
        ADD CONSTRAINT fk_tutor_reminders_student_id_tutor_students
        FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE SET NULL
    """,
    "CREATE INDEX ix_tutor_reminders_owner_id ON tutor_reminders (owner_id)",
)
_DOWNGRADE: tuple[str, ...] = ("DROP TABLE tutor_reminders",)


def upgrade() -> None:
    """Create the tutor reminder table."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop the tutor reminder table."""
    for statement in _DOWNGRADE:
        op.execute(statement)
