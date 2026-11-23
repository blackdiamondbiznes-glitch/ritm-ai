"""Tutor groups. One row is one class the owner teaches on a weekly slot."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TutorGroup(Base):
    """A named group with a level and a repeating time window."""

    __tablename__ = "tutor_groups"
    __table_args__ = (
        Index("ix_tutor_groups_owner_id", "owner_id"),
        Index("ix_tutor_groups_workspace_id", "workspace_id"),
        Index("ix_tutor_groups_enroll_code", "enroll_code", unique=True),
        CheckConstraint(
            "start_min >= 0 AND start_min < end_min AND end_min <= 1440",
            name="ck_tutor_groups_time",
        ),
        CheckConstraint("weekdays ~ '^[1-7](,[1-7])*$'", name="ck_tutor_groups_days"),
        CheckConstraint(
            "fee_mode IN ('none', 'monthly', 'package')",
            name="ck_tutor_groups_fee_mode",
        ),
        CheckConstraint(
            "fee_uzs >= 0 AND fee_uzs <= 1000000000",
            name="ck_tutor_groups_fee_uzs",
        ),
        CheckConstraint("due_days >= 0 AND due_days <= 31", name="ck_tutor_groups_due_days"),
        CheckConstraint(
            "remind_lesson_min IS NULL OR remind_lesson_min IN (15, 30, 60, 120)",
            name="ck_tutor_groups_remind_lesson",
        ),
        CheckConstraint(
            "remind_fee_days IS NULL OR remind_fee_days IN (1, 3, 7)",
            name="ck_tutor_groups_remind_fee",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[str | None] = mapped_column(String(40))
    weekdays: Mapped[str] = mapped_column(String(20), nullable=False)
    start_min: Mapped[int] = mapped_column(nullable=False)
    end_min: Mapped[int] = mapped_column(nullable=False)
    enroll_code: Mapped[str] = mapped_column(String(16), nullable=False)
    fee_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    fee_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    package_lessons: Mapped[int | None] = mapped_column(SmallInteger)
    billing_day: Mapped[int | None] = mapped_column(SmallInteger)
    due_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default="5"
    )
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    remind_lesson_min: Mapped[int | None] = mapped_column(
        SmallInteger, default=60, server_default="60"
    )
    remind_fee_days: Mapped[int | None] = mapped_column(SmallInteger, default=3, server_default="3")
    fee_in_group: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TutorGroupMember(Base):
    """A student placed in one group. The same student may join other groups."""

    __tablename__ = "tutor_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_tutor_group_members"),
        Index("ix_tutor_group_members_student_id", "student_id"),
        CheckConstraint(
            "status IN ('active', 'pending')",
            name="ck_tutor_group_members_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_groups.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    fee_override_uzs: Mapped[int | None] = mapped_column(Integer)
    billing_start: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
