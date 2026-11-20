"""Indexes for lookups that had none: poll answers by poll id, and two foreign keys.

Revision ID: 0013_lookup_indexes
Revises: 0012_user_prefs
Create Date: 2026-11-21

* ``quizzes.telegram_poll_id``: every native poll vote looks the quiz up by poll id.
* ``payments.duplicate_of_id`` and ``payment_events.actor_user_id``: foreign keys.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_lookup_indexes"
down_revision: str | None = "0012_user_prefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("ix_quizzes_telegram_poll_id", "quizzes", "telegram_poll_id"),
    ("ix_payments_duplicate_of_id", "payments", "duplicate_of_id"),
    ("ix_payment_events_actor_user_id", "payment_events", "actor_user_id"),
)


def upgrade() -> None:
    """Create the three indexes."""
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    """Drop the three indexes."""
    for name, table, _column in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
