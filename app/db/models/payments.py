"""Manual payment requests waiting for a super-admin review."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

METHOD_CARD = "manual_card"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_DRAFT = "draft"  # terms accepted, reference issued, receipt not sent yet
STATUS_DISPUTED = "disputed"  # owner objected to a rejection; back in the admin queue
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"
OPEN_STATUSES = (STATUS_PENDING, STATUS_DISPUTED)
REVIEWABLE = (STATUS_PENDING, STATUS_DISPUTED)
ALL_STATUSES = (
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_DISPUTED,
    STATUS_CANCELED,
    STATUS_EXPIRED,
)


class Payment(Base):
    """One owner's request to pay for a plan by card transfer."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_owner_id", "owner_id"),
        Index("ix_payments_plan_id", "plan_id"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_reviewed_by", "reviewed_by"),
        CheckConstraint("method IN ('manual_card')", name="method"),
        Index("uq_payments_ref_code", "ref_code", unique=True),
        Index("ix_payments_receipt_unique_id", "receipt_unique_id"),
        Index("ix_payments_duplicate_of_id", "duplicate_of_id"),
        CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'rejected', 'disputed', 'canceled', "
            "'expired')",
            name="status",
        ),
        CheckConstraint("requested_period_months IN (1, 3, 12)", name="months"),
        CheckConstraint("amount_uzs >= 0", name="amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default=METHOD_CARD)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_PENDING)
    requested_period_months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    receipt_file_id: Mapped[str | None] = mapped_column(String(256))
    note: Mapped[str | None] = mapped_column(Text)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_code: Mapped[str | None] = mapped_column(String(16))
    base_amount_uzs: Mapped[int | None] = mapped_column(Integer)
    receipt_unique_id: Mapped[str | None] = mapped_column(String(128))
    receipt_kind: Mapped[str | None] = mapped_column(String(16))
    payer_card_last4: Mapped[str | None] = mapped_column(String(4))
    transfer_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_version: Mapped[str | None] = mapped_column(String(32))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    is_fake: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    dispute_text: Mapped[str | None] = mapped_column(Text)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaymentEvent(Base):
    """Append-only history of one payment. A database trigger forbids UPDATE and DELETE."""

    __tablename__ = "payment_events"
    __table_args__ = (
        Index("ix_payment_events_payment_id", "payment_id"),
        Index("ix_payment_events_created_at", "created_at"),
        Index("ix_payment_events_actor_user_id", "actor_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    receipt_unique_id: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
