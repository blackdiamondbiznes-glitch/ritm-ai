"""Tutor cabinet lessons, optionally linked to a student.

Revision ID: 0015_tutor_lessons
Revises: 0014_tutor_students
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_tutor_lessons"
down_revision: str | None = "0014_tutor_students"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE tutor_lessons (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        student_id INTEGER,
        title VARCHAR(120) NOT NULL,
        status VARCHAR(16) NOT NULL,
        amount_uzs INTEGER NOT NULL DEFAULT 0,
        starts_at TIMESTAMPTZ,
        note VARCHAR(300),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE tutor_lessons
        ADD CONSTRAINT fk_tutor_lessons_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_lessons
        ADD CONSTRAINT fk_tutor_lessons_student_id_tutor_students
        FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE SET NULL
    """,
    """
    ALTER TABLE tutor_lessons
        ADD CONSTRAINT ck_tutor_lessons_status
        CHECK (status IN ('scheduled', 'done', 'cancelled'))
    """,
    """
    ALTER TABLE tutor_lessons
        ADD CONSTRAINT ck_tutor_lessons_amount
        CHECK (amount_uzs >= 0 AND amount_uzs <= 1000000000)
    """,
    "CREATE INDEX ix_tutor_lessons_owner_id ON tutor_lessons (owner_id)",
    "CREATE INDEX ix_tutor_lessons_student_id ON tutor_lessons (student_id)",
)

_DOWNGRADE: tuple[str, ...] = ("DROP TABLE tutor_lessons",)


def upgrade() -> None:
    """Create the tutor lesson table."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop the tutor lesson table."""
    for statement in _DOWNGRADE:
        op.execute(statement)
