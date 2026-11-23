"""One topic taught to a group, and the 0–10 mark each student received."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TutorTopic(Base):
    """A lesson topic on one day for one group."""

    __tablename__ = "tutor_topics"
    __table_args__ = (
        Index("ix_tutor_topics_group_id", "group_id"),
        CheckConstraint(
            "homework IS NULL OR char_length(homework) <= 1000",
            name="ck_tutor_topics_homework",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_groups.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    held_on: Mapped[date] = mapped_column(Date, nullable=False)
    homework: Mapped[str | None] = mapped_column(Text)
    homework_due: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TutorScore(Base):
    """A mark from 0 to 10. A missing row means the student was not graded."""

    __tablename__ = "tutor_scores"
    __table_args__ = (
        UniqueConstraint("topic_id", "student_id", name="uq_tutor_scores"),
        Index("ix_tutor_scores_student_id", "student_id"),
        CheckConstraint("score >= 0 AND score <= 10", name="ck_tutor_scores_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_topics.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
