"""Per-user preferences: chosen UI language flag, notification switches, default timezone.

Revision ID: 0012_user_prefs
Revises: 0011_usage_daily
Create Date: 2026-11-21

* ``ui_language_set``: /start asks for the language until the user picks one. Rows that
  exist before this migration are marked as already chosen, so current users are not asked.
* ``notify_reports`` / ``notify_expiry``: opt-outs for the scheduled trial reports and the
  trial expiry notice (payment results and chat-removed alerts are always sent).
* ``default_timezone``: preselected zone for the profile of newly connected chats.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_user_prefs"
down_revision: str | None = "0011_usage_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the preference columns."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop the preference columns."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN ui_language_set BOOLEAN NOT NULL DEFAULT false",
    "UPDATE users SET ui_language_set = true",
    "ALTER TABLE users ADD COLUMN notify_reports BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE users ADD COLUMN notify_expiry BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE users ADD COLUMN default_timezone VARCHAR(64)",
)

_DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE users DROP COLUMN default_timezone",
    "ALTER TABLE users DROP COLUMN notify_expiry",
    "ALTER TABLE users DROP COLUMN notify_reports",
    "ALTER TABLE users DROP COLUMN ui_language_set",
)
