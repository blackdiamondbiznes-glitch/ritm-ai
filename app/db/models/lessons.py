"""Tutor cabinet lessons. One row is one lesson of one owner."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUSES = ("scheduled", "done", "cancelled")
SOURCES = ("manual", "schedule")


class TutorLesson(Base):
    """A lesson the owner scheduled, finished, or cancelled.

    A group session sets `group_id`. `planned_at` is the slot from the weekly
    timetable and stays put when the teacher moves `starts_at`.
    """

    __tablename__ = "tutor_lessons"
    __table_args__ = (
        Index("ix_tutor_lessons_owner_id", "owner_id"),
        Index("ix_tutor_lessons_student_id", "student_id"),
        Index("ix_tutor_lessons_group_starts", "group_id", "starts_at"),
        Index(
            "uq_tutor_lessons_group_slot",
            "group_id",
            "planned_at",
            unique=True,
            postgresql_where=text("planned_at IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('scheduled', 'done', 'cancelled')",
            name="ck_tutor_lessons_status",
        ),
        CheckConstraint(
            "amount_uzs >= 0 AND amount_uzs <= 1000000000",
            name="ck_tutor_lessons_amount",
        ),
        CheckConstraint(
            "source IN ('manual', 'schedule')",
            name="ck_tutor_lessons_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="SET NULL")
    )
    group_id: Mapped[int | None] = mapped_column(ForeignKey("tutor_groups.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="manual", server_default="manual"
    )
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
