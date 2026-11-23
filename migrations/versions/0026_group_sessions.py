"""Dated group sessions live on tutor_lessons.

Revision ID: 0026_group_sessions
Revises: 0025_workspaces
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_group_sessions"
down_revision: str | None = "0025_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    ALTER TABLE tutor_lessons
        ADD COLUMN group_id INTEGER,
        ADD COLUMN workspace_id INTEGER,
        ADD COLUMN ends_at TIMESTAMPTZ,
        ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'manual',
        ADD COLUMN planned_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE tutor_lessons
        ADD CONSTRAINT fk_tutor_lessons_group_id_tutor_groups
            FOREIGN KEY (group_id) REFERENCES tutor_groups (id) ON DELETE CASCADE,
        ADD CONSTRAINT fk_tutor_lessons_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
        ADD CONSTRAINT ck_tutor_lessons_source
            CHECK (source IN ('manual', 'schedule'))
    """,
    """
    INSERT INTO workspaces (owner_id, vertical, name)
    SELECT u.id, 'tutor', left(coalesce(nullif(btrim(u.full_name), ''), 'Kabinet'), 80)
    FROM users u
    WHERE u.id IN (SELECT owner_id FROM tutor_lessons)
      AND NOT EXISTS (
          SELECT 1 FROM workspaces w
          WHERE w.owner_id = u.id AND w.vertical = 'tutor'
      )
    """,
    """
    UPDATE tutor_lessons AS row
    SET workspace_id = space.id
    FROM workspaces AS space
    WHERE space.owner_id = row.owner_id AND space.vertical = 'tutor'
    """,
    "ALTER TABLE tutor_lessons ALTER COLUMN workspace_id SET NOT NULL",
    """
    CREATE UNIQUE INDEX uq_tutor_lessons_group_slot
        ON tutor_lessons (group_id, planned_at)
        WHERE planned_at IS NOT NULL
    """,
    "CREATE INDEX ix_tutor_lessons_group_starts ON tutor_lessons (group_id, starts_at)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX ix_tutor_lessons_group_starts",
    "DROP INDEX uq_tutor_lessons_group_slot",
    "ALTER TABLE tutor_lessons DROP CONSTRAINT ck_tutor_lessons_source",
    "ALTER TABLE tutor_lessons DROP CONSTRAINT fk_tutor_lessons_workspace_id_workspaces",
    "ALTER TABLE tutor_lessons DROP CONSTRAINT fk_tutor_lessons_group_id_tutor_groups",
    """
    ALTER TABLE tutor_lessons
        DROP COLUMN planned_at,
        DROP COLUMN source,
        DROP COLUMN ends_at,
        DROP COLUMN workspace_id,
        DROP COLUMN group_id
    """,
)


def upgrade() -> None:
    """Attach a group slot to each lesson and backfill the cabinet id."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove the session columns. Lesson rows stay."""
    for statement in _DOWNGRADE:
        op.execute(statement)
