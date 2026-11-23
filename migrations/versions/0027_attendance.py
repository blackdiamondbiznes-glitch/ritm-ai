"""One attendance mark per student and lesson.

Revision ID: 0027_attendance
Revises: 0026_group_sessions
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_attendance"
down_revision: str | None = "0026_group_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE tutor_attendance (
        id SERIAL PRIMARY KEY,
        lesson_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status VARCHAR(16) NOT NULL,
        note VARCHAR(200),
        marked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_tutor_attendance_lesson_id_tutor_lessons
            FOREIGN KEY (lesson_id) REFERENCES tutor_lessons (id) ON DELETE CASCADE,
        CONSTRAINT fk_tutor_attendance_student_id_tutor_students
            FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE CASCADE,
        CONSTRAINT ck_tutor_attendance_status
            CHECK (status IN ('present', 'absent', 'late', 'excused')),
        CONSTRAINT uq_tutor_attendance_lesson_student UNIQUE (lesson_id, student_id)
    )
    """,
    """
    CREATE INDEX ix_tutor_attendance_student_lesson
        ON tutor_attendance (student_id, lesson_id)
    """,
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX ix_tutor_attendance_student_lesson",
    "DROP TABLE tutor_attendance",
)


def upgrade() -> None:
    """Store one mark per student on a lesson."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove attendance marks."""
    for statement in _DOWNGRADE:
        op.execute(statement)
