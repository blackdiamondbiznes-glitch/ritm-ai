"""Tutor groups and the students who attend each weekly slot.

Revision ID: 0018_tutor_groups
Revises: 0017_tutor_reminders
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_tutor_groups"
down_revision: str | None = "0017_tutor_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE tutor_groups (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        name VARCHAR(80) NOT NULL,
        level VARCHAR(40),
        weekdays VARCHAR(20) NOT NULL,
        start_min INTEGER NOT NULL,
        end_min INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE tutor_groups
        ADD CONSTRAINT fk_tutor_groups_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_groups
        ADD CONSTRAINT ck_tutor_groups_time
        CHECK (start_min >= 0 AND start_min < end_min AND end_min <= 1440)
    """,
    """
    ALTER TABLE tutor_groups
        ADD CONSTRAINT ck_tutor_groups_days
        CHECK (weekdays ~ '^[1-7](,[1-7])*$')
    """,
    "CREATE INDEX ix_tutor_groups_owner_id ON tutor_groups (owner_id)",
    """
    CREATE TABLE tutor_group_members (
        id SERIAL PRIMARY KEY,
        group_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL
    )
    """,
    """
    ALTER TABLE tutor_group_members
        ADD CONSTRAINT fk_tutor_group_members_group_id_tutor_groups
        FOREIGN KEY (group_id) REFERENCES tutor_groups (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_group_members
        ADD CONSTRAINT fk_tutor_group_members_student_id_tutor_students
        FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_group_members
        ADD CONSTRAINT uq_tutor_group_members UNIQUE (group_id, student_id)
    """,
    "CREATE INDEX ix_tutor_group_members_student_id ON tutor_group_members (student_id)",
)
_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE tutor_group_members",
    "DROP TABLE tutor_groups",
)


def upgrade() -> None:
    """Create tutor groups and memberships."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop tutor groups and memberships."""
    for statement in _DOWNGRADE:
        op.execute(statement)
