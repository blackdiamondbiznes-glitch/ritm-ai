"""One Telegram account can hold only one student card per teacher.

Duplicates are unlinked (telegram_id set to NULL on every row except the lowest
id in each owner + telegram pair). Downgrade drops the index only. The unlinking
is not reversed.

Revision ID: 0022_student_telegram_unique
Revises: 0021_enroll_approval
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_student_telegram_unique"
down_revision: str | None = "0021_enroll_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNLINK = """
UPDATE tutor_students AS extra
SET telegram_id = NULL
WHERE extra.id IN (
    SELECT id FROM (
        SELECT id, row_number() OVER (
            PARTITION BY owner_id, telegram_id ORDER BY id
        ) AS n
        FROM tutor_students
        WHERE telegram_id IS NOT NULL
    ) ranked
    WHERE n > 1
)
"""


def upgrade() -> None:
    """Keep the oldest card and forbid a second card for the same account."""
    op.execute(_UNLINK)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_tutor_students_owner_telegram
        ON tutor_students (owner_id, telegram_id)
        WHERE telegram_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Drop the unique index. Cleared duplicate telegram ids stay cleared."""
    op.execute("DROP INDEX uq_tutor_students_owner_telegram")
