"""Align quizzes with the master schema. Channels use a private deep link.

Revision ID: 0004_quiz_align
Revises: 0003_quiz
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_quiz_align"
down_revision: str | None = "0003_quiz"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add mode, source post and per-user answers."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Restore the phase-3 draft columns."""
    for statement in _DOWNGRADE:
        op.execute(statement)


_UPGRADE: tuple[str, ...] = (
    "ALTER TABLE quizzes ADD COLUMN content_item_id INTEGER",
    """
    ALTER TABLE quizzes
        ADD CONSTRAINT fk_quizzes_content_item_id_content_items
        FOREIGN KEY (content_item_id) REFERENCES content_items (id)
    """,
    "CREATE INDEX ix_quizzes_content_item_id ON quizzes (content_item_id)",
    "ALTER TABLE quizzes ADD COLUMN explanation TEXT",
    "ALTER TABLE quizzes ADD COLUMN mode VARCHAR(32)",
    "UPDATE quizzes SET mode = 'private_deeplink' WHERE mode IS NULL",
    "ALTER TABLE quizzes ALTER COLUMN mode SET NOT NULL",
    """
    ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_mode
        CHECK (mode IN ('private_deeplink', 'group_native'))
    """,
    "ALTER TABLE quizzes ADD COLUMN telegram_poll_id VARCHAR(64)",
    "ALTER TABLE quizzes DROP COLUMN IF EXISTS slot",
    "ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_correct",
    """
    ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_correct
        CHECK (correct_index >= 0 AND correct_index <= 9)
    """,
    "DELETE FROM quiz_answers",
    "ALTER TABLE quiz_answers ADD COLUMN user_id INTEGER",
    "ALTER TABLE quiz_answers ADD COLUMN chosen_index INTEGER",
    "ALTER TABLE quiz_answers ADD COLUMN is_correct BOOLEAN",
    "ALTER TABLE quiz_answers ADD COLUMN answered_at TIMESTAMPTZ",
    "ALTER TABLE quiz_answers DROP CONSTRAINT IF EXISTS uq_quiz_answers_user",
    "ALTER TABLE quiz_answers DROP CONSTRAINT IF EXISTS ck_quiz_answers_choice",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS telegram_user_id",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS choice",
    "ALTER TABLE quiz_answers ALTER COLUMN user_id SET NOT NULL",
    "ALTER TABLE quiz_answers ALTER COLUMN chosen_index SET NOT NULL",
    "ALTER TABLE quiz_answers ALTER COLUMN is_correct SET NOT NULL",
    "ALTER TABLE quiz_answers ALTER COLUMN answered_at SET NOT NULL",
    """
    ALTER TABLE quiz_answers
        ADD CONSTRAINT uq_quiz_answers_user UNIQUE (quiz_id, user_id)
    """,
    """
    ALTER TABLE quiz_answers
        ADD CONSTRAINT fk_quiz_answers_user_id_users FOREIGN KEY (user_id) REFERENCES users (id)
    """,
    """
    ALTER TABLE quiz_answers ADD CONSTRAINT ck_quiz_answers_choice
        CHECK (chosen_index >= 0 AND chosen_index <= 9)
    """,
    "CREATE INDEX ix_quiz_answers_user_id ON quiz_answers (user_id)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_quiz_answers_user_id",
    "ALTER TABLE quiz_answers DROP CONSTRAINT IF EXISTS ck_quiz_answers_choice",
    "ALTER TABLE quiz_answers DROP CONSTRAINT IF EXISTS fk_quiz_answers_user_id_users",
    "ALTER TABLE quiz_answers DROP CONSTRAINT IF EXISTS uq_quiz_answers_user",
    "ALTER TABLE quiz_answers ADD COLUMN telegram_user_id BIGINT",
    "ALTER TABLE quiz_answers ADD COLUMN choice INTEGER",
    "UPDATE quiz_answers SET telegram_user_id = 0, choice = chosen_index",
    "ALTER TABLE quiz_answers ALTER COLUMN telegram_user_id SET NOT NULL",
    "ALTER TABLE quiz_answers ALTER COLUMN choice SET NOT NULL",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS user_id",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS chosen_index",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS is_correct",
    "ALTER TABLE quiz_answers DROP COLUMN IF EXISTS answered_at",
    """
    ALTER TABLE quiz_answers
        ADD CONSTRAINT uq_quiz_answers_user UNIQUE (quiz_id, telegram_user_id)
    """,
    """
    ALTER TABLE quiz_answers ADD CONSTRAINT ck_quiz_answers_choice
        CHECK (choice >= 0 AND choice <= 3)
    """,
    "ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_correct",
    """
    ALTER TABLE quizzes ADD CONSTRAINT ck_quizzes_correct
        CHECK (correct_index >= 0 AND correct_index <= 3)
    """,
    "ALTER TABLE quizzes ADD COLUMN slot VARCHAR(32)",
    "UPDATE quizzes SET slot = 'legacy' WHERE slot IS NULL",
    "ALTER TABLE quizzes ALTER COLUMN slot SET NOT NULL",
    "ALTER TABLE quizzes DROP COLUMN IF EXISTS telegram_poll_id",
    "ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS ck_quizzes_mode",
    "ALTER TABLE quizzes DROP COLUMN IF EXISTS mode",
    "ALTER TABLE quizzes DROP COLUMN IF EXISTS explanation",
    "DROP INDEX IF EXISTS ix_quizzes_content_item_id",
    "ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS fk_quizzes_content_item_id_content_items",
    "ALTER TABLE quizzes DROP COLUMN IF EXISTS content_item_id",
)
