"""Teacher approval for students who join a group from a link.

Revision ID: 0021_enroll_approval
Revises: 0020_group_enroll
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_enroll_approval"
down_revision: str | None = "0020_group_enroll"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE tutor_group_members ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'",
    """
    ALTER TABLE tutor_group_members
    ADD CONSTRAINT ck_tutor_group_members_status CHECK (status IN ('active', 'pending'))
    """,
    "ALTER TABLE tutor_group_members ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE tutor_students DROP CONSTRAINT ck_tutor_students_status",
    """
    ALTER TABLE tutor_students
    ADD CONSTRAINT ck_tutor_students_status
    CHECK (status IN ('paid', 'debtor', 'inactive', 'pending'))
    """,
)
_DOWNGRADE: tuple[str, ...] = (
    "DELETE FROM tutor_group_members WHERE status = 'pending'",
    "DELETE FROM tutor_students WHERE status = 'pending'",
    "ALTER TABLE tutor_students DROP CONSTRAINT ck_tutor_students_status",
    """
    ALTER TABLE tutor_students
    ADD CONSTRAINT ck_tutor_students_status
    CHECK (status IN ('paid', 'debtor', 'inactive'))
    """,
    "ALTER TABLE tutor_group_members DROP CONSTRAINT ck_tutor_group_members_status",
    "ALTER TABLE tutor_group_members DROP COLUMN created_at",
    "ALTER TABLE tutor_group_members DROP COLUMN status",
)


def upgrade() -> None:
    """Let a membership and a student card wait for the teacher."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop pending rows, then the approval columns and the extra status."""
    for statement in _DOWNGRADE:
        op.execute(statement)
