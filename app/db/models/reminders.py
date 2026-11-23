"""Tutor cabinet reminders sent to the owner in private chat."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TutorReminder(Base):
    """One reminder. `queued_at` stops a second job. `sent_at` means it went out."""

    __tablename__ = "tutor_reminders"
    __table_args__ = (
        Index("ix_tutor_reminders_owner_id", "owner_id"),
        Index(
            "ix_tutor_reminders_due",
            "send_at",
            postgresql_where=text("queued_at IS NULL"),
        ),
        CheckConstraint(
            "audience IN ('owner', 'student', 'group')",
            name="ck_tutor_reminders_audience",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="SET NULL")
    )
    group_id: Mapped[int | None] = mapped_column(ForeignKey("tutor_groups.id", ondelete="SET NULL"))
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False, default="owner", server_default="owner"
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
