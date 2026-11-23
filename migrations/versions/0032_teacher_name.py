"""Teacher display name shown to students instead of the Telegram name.

Revision ID: 0032_teacher_name
Revises: 0031_tutor_reports
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_teacher_name"
down_revision: str | None = "0031_tutor_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A nullable column: instant on Postgres, no rewrite, no default."""
    op.add_column("users", sa.Column("teacher_name", sa.String(length=80), nullable=True))


def downgrade() -> None:
    """Drop the display name."""
    op.drop_column("users", "teacher_name")
