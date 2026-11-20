"""Per-chat switch that lets Telegram admins edit schedules in the Mini App.

Revision ID: 0009_admin_edit
Revises: 0008_ops
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_admin_edit"
down_revision: str | None = "0008_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add chats.admins_can_edit, off by default."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove chats.admins_can_edit."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE chats ADD COLUMN admins_can_edit BOOLEAN NOT NULL DEFAULT false",
)

_DOWNGRADE: tuple[str, ...] = ("ALTER TABLE chats DROP COLUMN IF EXISTS admins_can_edit",)
