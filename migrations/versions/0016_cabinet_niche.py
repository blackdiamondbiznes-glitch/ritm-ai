"""Remember which owners turned on the tutor cabinet.

Revision ID: 0016_cabinet_niche
Revises: 0015_tutor_lessons
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_cabinet_niche"
down_revision: str | None = "0015_tutor_lessons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN cabinet_niche VARCHAR(16)",
    """
    ALTER TABLE users
        ADD CONSTRAINT ck_users_cabinet_niche
        CHECK (cabinet_niche IS NULL OR cabinet_niche IN ('tutor'))
    """,
)
_DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE users DROP CONSTRAINT ck_users_cabinet_niche",
    "ALTER TABLE users DROP COLUMN cabinet_niche",
)


def upgrade() -> None:
    """Add the cabinet niche flag."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove the cabinet niche flag."""
    for statement in _DOWNGRADE:
        op.execute(statement)
