"""Rename Agency to Ultra and set published prices.

Revision ID: 0007_pricing
Revises: 0006_payments
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_pricing"
down_revision: str | None = "0006_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply Ultra name and the current monthly prices."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Restore the previous plan name and prices."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    "UPDATE plans SET name = 'Ultra' WHERE code = 'agency'",
    "UPDATE plans SET price_uzs = 29000, founder_price_uzs = 20300 WHERE code = 'start'",
    "UPDATE plans SET price_uzs = 39000, founder_price_uzs = 27300 WHERE code = 'pro'",
    "UPDATE plans SET price_uzs = 69000, founder_price_uzs = 48300 WHERE code = 'agency'",
)

_DOWNGRADE: tuple[str, ...] = (
    "UPDATE plans SET name = 'Agency' WHERE code = 'agency'",
    "UPDATE plans SET price_uzs = 99000, founder_price_uzs = 69000 WHERE code = 'start'",
    "UPDATE plans SET price_uzs = 249000, founder_price_uzs = 149000 WHERE code = 'pro'",
    "UPDATE plans SET price_uzs = 799000, founder_price_uzs = 499000 WHERE code = 'agency'",
)
