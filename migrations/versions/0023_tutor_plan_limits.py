"""Cabinet size limits on each plan.

Revision ID: 0023_tutor_plan_limits
Revises: 0022_student_telegram_unique
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_tutor_plan_limits"
down_revision: str | None = "0022_student_telegram_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE plans ADD COLUMN max_tutor_groups INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE plans ADD COLUMN max_tutor_students INTEGER NOT NULL DEFAULT 40",
    "UPDATE plans SET max_tutor_groups = 2, max_tutor_students = 40 WHERE code = 'free'",
    "UPDATE plans SET max_tutor_groups = 4, max_tutor_students = 80 WHERE code = 'start'",
    "UPDATE plans SET max_tutor_groups = 10, max_tutor_students = 250 WHERE code = 'pro'",
    "UPDATE plans SET max_tutor_groups = 30, max_tutor_students = 1000 WHERE code = 'agency'",
)
_DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE plans DROP COLUMN max_tutor_students",
    "ALTER TABLE plans DROP COLUMN max_tutor_groups",
)


def upgrade() -> None:
    """Store how many groups and students each plan may hold."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove the cabinet limits from plans."""
    for statement in _DOWNGRADE:
        op.execute(statement)
