"""Online lesson link on a lesson or group session.

Revision ID: 0034_meeting_url
Revises: 0033_widget_messages
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_meeting_url"
down_revision: str | None = "0033_widget_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A nullable column: instant on Postgres, no rewrite, no default."""
    op.add_column("tutor_lessons", sa.Column("meeting_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Drop the lesson link."""
    op.drop_column("tutor_lessons", "meeting_url")
