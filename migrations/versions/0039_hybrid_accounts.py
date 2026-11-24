"""Email accounts and EduFlow role assignments.

Revision ID: 0039_hybrid_accounts
Revises: 0038_workspace_billing
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_hybrid_accounts"
down_revision: str | None = "0038_workspace_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow email-only accounts while keeping Telegram IDs unique."""
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    op.add_column("users", sa.Column("account_role", sa.String(length=32), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_check_constraint(
        "ck_users_account_role",
        "users",
        "account_role IS NULL OR account_role IN ('teacher', 'student', 'community_owner')",
    )


def downgrade() -> None:
    """Refuse to discard email-account data when reverting this migration."""
    bind = op.get_bind()
    account_data = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE telegram_id IS NULL "
            "OR email IS NOT NULL OR password_hash IS NOT NULL OR account_role IS NOT NULL)"
        )
    ).scalar()
    if account_data:
        raise RuntimeError("Cannot downgrade while hybrid-account data exists")
    op.drop_constraint("ck_users_account_role", "users", type_="check")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "account_role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=False)
