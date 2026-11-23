"""Store widget message ids and allow attendance notices.

Revision ID: 0033_widget_messages
Revises: 0032_teacher_name
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_widget_messages"
down_revision: str | None = "0032_teacher_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "lesson",
    "fee_due",
    "fee_overdue",
    "cancel",
    "move",
    "announce",
    "manual",
    "homework",
    "attendance",
)
_OLD = ", ".join(f"'{item}'" for item in _KINDS if item != "attendance")
_NEW = ", ".join(f"'{item}'" for item in _KINDS)


def upgrade() -> None:
    """Add the lookup table and the attendance notice kind."""
    op.create_table(
        "tutor_widget_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("kind", "ref_id", "telegram_id", name="uq_tutor_widget_messages_ref"),
    )
    op.execute("ALTER TABLE tutor_notifications DROP CONSTRAINT ck_tutor_notifications_kind")
    op.execute(
        f"ALTER TABLE tutor_notifications "
        f"ADD CONSTRAINT ck_tutor_notifications_kind CHECK (kind IN ({_NEW}))"
    )


def downgrade() -> None:
    """Remove attendance from the notice kinds and drop the table."""
    op.execute("ALTER TABLE tutor_notifications DROP CONSTRAINT ck_tutor_notifications_kind")
    op.execute(
        f"ALTER TABLE tutor_notifications "
        f"ADD CONSTRAINT ck_tutor_notifications_kind CHECK (kind IN ({_OLD}))"
    )
    op.drop_table("tutor_widget_messages")
