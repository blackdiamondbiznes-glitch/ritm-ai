"""Topic marks for a group, and a Telegram link on each student.

Revision ID: 0019_topic_scores
Revises: 0018_tutor_groups
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_topic_scores"
down_revision: str | None = "0018_tutor_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE tutor_students ADD COLUMN telegram_id BIGINT",
    "ALTER TABLE tutor_students ADD COLUMN join_code VARCHAR(16)",
    """
    UPDATE tutor_students
    SET join_code = substr(md5(id::text || random()::text), 1, 10)
    WHERE join_code IS NULL
    """,
    "ALTER TABLE tutor_students ALTER COLUMN join_code SET NOT NULL",
    "CREATE UNIQUE INDEX ix_tutor_students_join_code ON tutor_students (join_code)",
    "CREATE INDEX ix_tutor_students_telegram_id ON tutor_students (telegram_id)",
    """
    CREATE TABLE tutor_topics (
        id SERIAL PRIMARY KEY,
        group_id INTEGER NOT NULL,
        title VARCHAR(120) NOT NULL,
        held_on DATE NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE tutor_topics
        ADD CONSTRAINT fk_tutor_topics_group_id_tutor_groups
        FOREIGN KEY (group_id) REFERENCES tutor_groups (id) ON DELETE CASCADE
    """,
    "CREATE INDEX ix_tutor_topics_group_id ON tutor_topics (group_id)",
    """
    CREATE TABLE tutor_scores (
        id SERIAL PRIMARY KEY,
        topic_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        score INTEGER NOT NULL
    )
    """,
    """
    ALTER TABLE tutor_scores
        ADD CONSTRAINT fk_tutor_scores_topic_id_tutor_topics
        FOREIGN KEY (topic_id) REFERENCES tutor_topics (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_scores
        ADD CONSTRAINT fk_tutor_scores_student_id_tutor_students
        FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE CASCADE
    """,
    "ALTER TABLE tutor_scores ADD CONSTRAINT uq_tutor_scores UNIQUE (topic_id, student_id)",
    "ALTER TABLE tutor_scores ADD CONSTRAINT ck_tutor_scores_score CHECK (score >= 0 AND score <= 10)",
    "CREATE INDEX ix_tutor_scores_student_id ON tutor_scores (student_id)",
)
_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE tutor_scores",
    "DROP TABLE tutor_topics",
    "DROP INDEX ix_tutor_students_telegram_id",
    "DROP INDEX ix_tutor_students_join_code",
    "ALTER TABLE tutor_students DROP COLUMN telegram_id",
    "ALTER TABLE tutor_students DROP COLUMN join_code",
)


def upgrade() -> None:
    """Add topic marks and the student invite code."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove topic marks and the student invite code."""
    for statement in _DOWNGRADE:
        op.execute(statement)
