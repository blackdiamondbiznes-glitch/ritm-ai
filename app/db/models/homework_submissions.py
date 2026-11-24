"""Student answers to tutor homework topics."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TutorHomeworkSubmission(Base):
    """One editable answer per student and topic, with a teacher grade."""

    __tablename__ = "tutor_homework_submissions"
    __table_args__ = (
        UniqueConstraint("topic_id", "student_id", name="uq_tutor_homework_submission"),
        Index("ix_tutor_homework_submission_topic_id", "topic_id"),
        Index("ix_tutor_homework_submission_student_id", "student_id"),
        CheckConstraint(
            "status IN ('submitted', 'graded')",
            name="ck_tutor_homework_submission_status",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 10", name="ck_tutor_homework_score"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="ck_tutor_homework_body"),
        CheckConstraint(
            "feedback IS NULL OR char_length(feedback) <= 1000",
            name="ck_tutor_homework_feedback",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_topics.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="submitted")
    score: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
