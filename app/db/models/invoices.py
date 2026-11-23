"""Invoices for a group's monthly fee or lesson package, and the payments on them."""

from datetime import date, datetime

from sqlalchemy import (
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

KINDS = ("monthly", "package")
INVOICE_STATUSES = ("due", "paid", "overdue", "waived")
METHODS = ("cash", "card", "transfer", "other")


class TutorInvoice(Base):
    """One bill for one student in one group. A package tracks lessons used."""

    __tablename__ = "tutor_invoices"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "student_id", "kind", "period_start", name="uq_tutor_invoices_period"
        ),
        Index("ix_tutor_invoices_workspace_status", "workspace_id", "status"),
        Index("ix_tutor_invoices_student_id", "student_id"),
        CheckConstraint("kind IN ('monthly', 'package')", name="ck_tutor_invoices_kind"),
        CheckConstraint(
            "status IN ('due', 'paid', 'overdue', 'waived')",
            name="ck_tutor_invoices_status",
        ),
        CheckConstraint(
            "amount_uzs >= 0 AND amount_uzs <= 1000000000",
            name="ck_tutor_invoices_amount",
        ),
        CheckConstraint("paid_uzs >= 0 AND paid_uzs <= amount_uzs", name="ck_tutor_invoices_paid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_groups.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_students.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date)
    lessons_total: Mapped[int | None] = mapped_column(SmallInteger)
    lessons_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TutorFeePayment(Base):
    """Money recorded against one invoice. This is the teacher's income, not a Ritm plan."""

    __tablename__ = "tutor_fee_payments"
    __table_args__ = (
        Index("ix_tutor_fee_payments_invoice_id", "invoice_id"),
        CheckConstraint(
            "amount_uzs > 0 AND amount_uzs <= 1000000000",
            name="ck_tutor_fee_payments_amount",
        ),
        CheckConstraint(
            "method IN ('cash', 'card', 'transfer', 'other')",
            name="ck_tutor_fee_payments_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("tutor_invoices.id", ondelete="CASCADE"), nullable=False
    )
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
