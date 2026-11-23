"""Speed up the scan for reminders that have not been queued.

Revision ID: 0024_reminder_due_index
Revises: 0023_tutor_plan_limits
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_reminder_due_index"
down_revision: str | None = "0023_tutor_plan_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Index reminders that still need a job."""
    op.execute(
        """
        CREATE INDEX ix_tutor_reminders_due
        ON tutor_reminders (send_at)
        WHERE queued_at IS NULL
        """
    )


def downgrade() -> None:
    """Remove the due-reminder index."""
    op.execute("DROP INDEX ix_tutor_reminders_due")
