"""One attendance mark for one student on one lesson."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUSES = ("present", "absent", "late", "excused")


class TutorAttendance(Base):
    """Present, absent, late, or excused for one student in one session."""

    __tablename__ = "tutor_attendance"
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_tutor_attendance_lesson_student"),
        Index("ix_tutor_attendance_student_lesson", "student_id", "lesson_id"),
        CheckConstraint(
            "status IN ('present', 'absent', 'late', 'excused')",
            name="ck_tutor_attendance_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_lessons.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
