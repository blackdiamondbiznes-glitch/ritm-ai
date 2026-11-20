"""Manual payments, founder flags, locked prices and notification dedup.

Revision ID: 0006_payments
Revises: 0005_leaderboard
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_payments"
down_revision: str | None = "0005_leaderboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add payment tables and founder columns."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove payment tables and founder columns."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN is_founder BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN founder_since TIMESTAMPTZ",
    "ALTER TABLE subscriptions ADD COLUMN price_uzs INTEGER",
    "ALTER TABLE plans ADD COLUMN founder_price_uzs INTEGER NOT NULL DEFAULT 0",
    "UPDATE plans SET founder_price_uzs = 0 WHERE code = 'free'",
    "UPDATE plans SET founder_price_uzs = 69000 WHERE code = 'start'",
    "UPDATE plans SET founder_price_uzs = 149000 WHERE code = 'pro'",
    "UPDATE plans SET founder_price_uzs = 499000 WHERE code = 'agency'",
    """
    CREATE TABLE payments (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        amount_uzs INTEGER NOT NULL,
        method VARCHAR(32) NOT NULL,
        status VARCHAR(16) NOT NULL,
        requested_period_months INTEGER NOT NULL DEFAULT 1,
        receipt_file_id VARCHAR(256),
        note TEXT,
        reject_reason TEXT,
        reviewed_by INTEGER,
        reviewed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT fk_payments_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id)
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT fk_payments_plan_id_plans
        FOREIGN KEY (plan_id) REFERENCES plans (id)
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT fk_payments_reviewed_by_users
        FOREIGN KEY (reviewed_by) REFERENCES users (id)
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT ck_payments_method CHECK (method IN ('manual_card'))
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT ck_payments_status
        CHECK (status IN ('pending', 'approved', 'rejected'))
    """,
    """
    ALTER TABLE payments
        ADD CONSTRAINT ck_payments_months
        CHECK (requested_period_months IN (1, 3, 12))
    """,
    "ALTER TABLE payments ADD CONSTRAINT ck_payments_amount CHECK (amount_uzs >= 0)",
    "CREATE INDEX ix_payments_owner_id ON payments (owner_id)",
    "CREATE INDEX ix_payments_plan_id ON payments (plan_id)",
    "CREATE INDEX ix_payments_status ON payments (status)",
    "CREATE INDEX ix_payments_reviewed_by ON payments (reviewed_by)",
    """
    CREATE TABLE notifications_log (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        chat_id INTEGER,
        chat_key INTEGER NOT NULL DEFAULT 0,
        kind VARCHAR(64) NOT NULL,
        sent_on DATE NOT NULL,
        sent_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE notifications_log
        ADD CONSTRAINT fk_notifications_log_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id)
    """,
    """
    ALTER TABLE notifications_log
        ADD CONSTRAINT fk_notifications_log_chat_id_chats
        FOREIGN KEY (chat_id) REFERENCES chats (id)
    """,
    """
    ALTER TABLE notifications_log
        ADD CONSTRAINT uq_notifications_log_once
        UNIQUE (owner_id, chat_key, kind, sent_on)
    """,
    "CREATE INDEX ix_notifications_log_owner_id ON notifications_log (owner_id)",
    "CREATE INDEX ix_notifications_log_chat_id ON notifications_log (chat_id)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE IF EXISTS notifications_log",
    "DROP TABLE IF EXISTS payments",
    "ALTER TABLE plans DROP COLUMN IF EXISTS founder_price_uzs",
    "ALTER TABLE subscriptions DROP COLUMN IF EXISTS price_uzs",
    "ALTER TABLE users DROP COLUMN IF EXISTS founder_since",
    "ALTER TABLE users DROP COLUMN IF EXISTS is_founder",
)
