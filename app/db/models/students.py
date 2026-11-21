"""Tutor cabinet students. One row is one student of one owner."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUSES = ("paid", "debtor", "inactive")


class TutorStudent(Base):
    """A student the owner tracks: paid, owing, or inactive."""

    __tablename__ = "tutor_students"
    __table_args__ = (
        Index("ix_tutor_students_owner_id", "owner_id"),
        CheckConstraint(
            "status IN ('paid', 'debtor', 'inactive')",
            name="ck_tutor_students_status",
        ),
        CheckConstraint(
            "amount_uzs >= 0 AND amount_uzs <= 1000000000",
            name="ck_tutor_students_amount",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
