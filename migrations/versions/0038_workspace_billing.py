"""Workspace roles, vertical plans, and workspace-scoped subscriptions.

Revision ID: 0038_workspace_billing
Revises: 0037_homework_submissions
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0038_workspace_billing"
down_revision: str | None = "0037_homework_submissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add vertical membership and plan entitlements without changing legacy billing."""
    op.execute("ALTER TABLE plans ADD COLUMN vertical VARCHAR(32)")
    op.execute("CREATE INDEX ix_plans_vertical ON plans (vertical)")
    op.execute(
        """
        ALTER TABLE subscriptions
        ADD COLUMN workspace_id INTEGER,
        ADD CONSTRAINT fk_subscriptions_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
        """
    )
    op.execute("DROP INDEX uq_subscriptions_one_open")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_subscriptions_one_open_legacy
        ON subscriptions (owner_id)
        WHERE status IN ('trial', 'active') AND workspace_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_subscriptions_one_open_workspace
        ON subscriptions (workspace_id)
        WHERE status IN ('trial', 'active') AND workspace_id IS NOT NULL
        """
    )
    op.execute("CREATE INDEX ix_subscriptions_workspace_id ON subscriptions (workspace_id)")
    op.execute(
        """
        CREATE TABLE workspace_members (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_workspace_members_workspace_id_workspaces
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
            CONSTRAINT fk_workspace_members_user_id_users
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT uq_workspace_members_user UNIQUE (workspace_id, user_id),
            CONSTRAINT ck_workspace_members_role
                CHECK (role IN ('owner', 'manager', 'teacher', 'student', 'member')),
            CONSTRAINT ck_workspace_members_status
                CHECK (status IN ('active', 'invited', 'suspended'))
        )
        """
    )
    op.execute("CREATE INDEX ix_workspace_members_user_id ON workspace_members (user_id)")
    op.execute(
        """
        INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT id, owner_id, 'owner' FROM workspaces
        ON CONFLICT (workspace_id, user_id) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE plan_entitlements (
            id SERIAL PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            feature_key VARCHAR(100) NOT NULL,
            feature_value JSONB NOT NULL,
            CONSTRAINT fk_plan_entitlements_plan_id_plans
                FOREIGN KEY (plan_id) REFERENCES plans (id) ON DELETE CASCADE,
            CONSTRAINT uq_plan_entitlements_feature UNIQUE (plan_id, feature_key),
            CONSTRAINT ck_plan_entitlements_feature_key CHECK (length(feature_key) > 0)
        )
        """
    )
    op.execute(
        """
        INSERT INTO plan_entitlements (plan_id, feature_key, feature_value)
        SELECT id, 'max_chats', to_jsonb(max_chats) FROM plans
        UNION ALL
        SELECT id, 'max_tutor_groups', to_jsonb(max_tutor_groups) FROM plans
        UNION ALL
        SELECT id, 'max_tutor_students', to_jsonb(max_tutor_students) FROM plans
        UNION ALL
        SELECT id, 'max_tutor_notifications_month',
               to_jsonb(max_tutor_notifications_month) FROM plans
        UNION ALL
        SELECT id, 'ai_generations_per_month', to_jsonb(ai_generations_per_month) FROM plans
        UNION ALL
        SELECT id, 'modules', to_jsonb(modules) FROM plans
        """
    )


def downgrade() -> None:
    """Remove workspace billing additions while preserving legacy subscriptions."""
    if not context.is_offline_mode():
        has_workspace_subscriptions = op.get_bind().execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM subscriptions WHERE workspace_id IS NOT NULL)")
        ).scalar()
        if has_workspace_subscriptions:
            raise RuntimeError("Cannot downgrade while workspace-scoped subscriptions exist")
    op.execute("DROP TABLE plan_entitlements")
    op.execute("DROP TABLE workspace_members")
    op.execute("DROP INDEX ix_subscriptions_workspace_id")
    op.execute("DROP INDEX uq_subscriptions_one_open_workspace")
    op.execute("DROP INDEX uq_subscriptions_one_open_legacy")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_subscriptions_one_open
        ON subscriptions (owner_id)
        WHERE status IN ('trial', 'active')
        """
    )
    op.execute(
        """
        ALTER TABLE subscriptions
        DROP CONSTRAINT fk_subscriptions_workspace_id_workspaces,
        DROP COLUMN workspace_id
        """
    )
    op.execute("DROP INDEX ix_plans_vertical")
    op.execute("ALTER TABLE plans DROP COLUMN vertical")
