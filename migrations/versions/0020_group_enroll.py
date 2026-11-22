"""Public registration code for each tutor group.

Revision ID: 0020_group_enroll
Revises: 0019_topic_scores
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_group_enroll"
down_revision: str | None = "0019_topic_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE tutor_groups ADD COLUMN enroll_code VARCHAR(16)",
    """
    UPDATE tutor_groups
    SET enroll_code = substr(md5(id::text || random()::text), 1, 10)
    WHERE enroll_code IS NULL
    """,
    "ALTER TABLE tutor_groups ALTER COLUMN enroll_code SET NOT NULL",
    "CREATE UNIQUE INDEX ix_tutor_groups_enroll_code ON tutor_groups (enroll_code)",
)
_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX ix_tutor_groups_enroll_code",
    "ALTER TABLE tutor_groups DROP COLUMN enroll_code",
)


def upgrade() -> None:
    """Add a registration code to every group."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove the registration code."""
    for statement in _DOWNGRADE:
        op.execute(statement)
