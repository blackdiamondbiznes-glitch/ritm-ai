"""Student homework submissions and teacher feedback.

Revision ID: 0040_homework_submissions
Revises: 0039_hybrid_accounts
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_homework_submissions"
down_revision: str | None = "0039_hybrid_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one submission per student and homework topic."""
    op.create_table(
        "tutor_homework_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("tutor_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("tutor_students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("topic_id", "student_id", name="uq_tutor_homework_submission"),
        sa.CheckConstraint(
            "status IN ('submitted', 'graded')", name="ck_tutor_homework_submission_status"
        ),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 10", name="ck_tutor_homework_score"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="ck_tutor_homework_body"),
        sa.CheckConstraint(
            "feedback IS NULL OR char_length(feedback) <= 1000",
            name="ck_tutor_homework_feedback",
        ),
    )
    op.create_index(
        "ix_tutor_homework_submission_topic_id",
        "tutor_homework_submissions",
        ["topic_id"],
    )
    op.create_index(
        "ix_tutor_homework_submission_student_id",
        "tutor_homework_submissions",
        ["student_id"],
    )


def downgrade() -> None:
    """Drop submissions and feedback."""
    op.drop_index(
        "ix_tutor_homework_submission_student_id", table_name="tutor_homework_submissions"
    )
    op.drop_index(
        "ix_tutor_homework_submission_topic_id", table_name="tutor_homework_submissions"
    )
    op.drop_table("tutor_homework_submissions")
