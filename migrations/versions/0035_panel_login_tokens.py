"""One-time sign-in links for the teacher web panel.

Revision ID: 0035_panel_login_tokens
Revises: 0034_meeting_url
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_panel_login_tokens"
down_revision: str | None = "0034_meeting_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A new small table; nothing existing is rewritten."""
    op.create_table(
        "panel_login_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("token_hash", name="uq_panel_login_tokens_token_hash"),
    )
    op.create_index("ix_panel_login_tokens_user_id", "panel_login_tokens", ["user_id"])


def downgrade() -> None:
    """Drop the sign-in links."""
    op.drop_index("ix_panel_login_tokens_user_id", table_name="panel_login_tokens")
    op.drop_table("panel_login_tokens")
