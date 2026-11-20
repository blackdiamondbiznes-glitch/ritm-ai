"""Operational state and the paid total on a subscription.

Revision ID: 0008_ops
Revises: 0007_pricing
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_ops"
down_revision: str | None = "0007_pricing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add system_state and paid_amount_uzs."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove system_state and paid_amount_uzs."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE system_state (
        key VARCHAR(64) PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE subscriptions ADD COLUMN paid_amount_uzs INTEGER",
)

_DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE subscriptions DROP COLUMN IF EXISTS paid_amount_uzs",
    "DROP TABLE IF EXISTS system_state",
)
