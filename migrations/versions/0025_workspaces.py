"""One workspace per owner and vertical. Groups and cards point at it.

Revision ID: 0025_workspaces
Revises: 0024_reminder_due_index
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025_workspaces"
down_revision: str | None = "0024_reminder_due_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE workspaces (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        vertical VARCHAR(32) NOT NULL DEFAULT 'tutor',
        name VARCHAR(80) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_workspaces_owner_id_users
            FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE,
        CONSTRAINT uq_workspaces_owner_vertical UNIQUE (owner_id, vertical)
    )
    """,
    "CREATE INDEX ix_workspaces_owner_id ON workspaces (owner_id)",
    """
    INSERT INTO workspaces (owner_id, vertical, name)
    SELECT owner_id, 'tutor', left(coalesce(nullif(btrim(full_name), ''), 'Kabinet'), 80)
    FROM (
        SELECT u.id AS owner_id, u.full_name
        FROM users u
        WHERE u.cabinet_niche = 'tutor'
           OR u.id IN (SELECT owner_id FROM tutor_groups)
           OR u.id IN (SELECT owner_id FROM tutor_students)
    ) owners
    """,
    """
    ALTER TABLE tutor_groups
        ADD COLUMN workspace_id INTEGER,
        ADD CONSTRAINT fk_tutor_groups_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_students
        ADD COLUMN workspace_id INTEGER,
        ADD CONSTRAINT fk_tutor_students_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
    """,
    """
    UPDATE tutor_groups AS row
    SET workspace_id = space.id
    FROM workspaces AS space
    WHERE space.owner_id = row.owner_id AND space.vertical = 'tutor'
    """,
    """
    UPDATE tutor_students AS row
    SET workspace_id = space.id
    FROM workspaces AS space
    WHERE space.owner_id = row.owner_id AND space.vertical = 'tutor'
    """,
    "ALTER TABLE tutor_groups ALTER COLUMN workspace_id SET NOT NULL",
    "ALTER TABLE tutor_students ALTER COLUMN workspace_id SET NOT NULL",
    "CREATE INDEX ix_tutor_groups_workspace_id ON tutor_groups (workspace_id)",
    "CREATE INDEX ix_tutor_students_workspace_id ON tutor_students (workspace_id)",
)
_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX ix_tutor_students_workspace_id",
    "DROP INDEX ix_tutor_groups_workspace_id",
    "ALTER TABLE tutor_students DROP COLUMN workspace_id",
    "ALTER TABLE tutor_groups DROP COLUMN workspace_id",
    "DROP TABLE workspaces",
)


def upgrade() -> None:
    """Backfill one tutor workspace for each existing teacher."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove workspace links and the workspace table."""
    for statement in _DOWNGRADE:
        op.execute(statement)
