"""One row per tutor notice and recipient. The unique key stops a second send."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

KINDS = ("lesson", "fee_due", "fee_overdue", "cancel", "move", "announce", "manual")
TARGETS = ("student", "group", "owner")
STATUSES = ("sent", "skipped", "failed")


class TutorNotice(Base):
    """A claimed delivery. `failed` means a job may still retry it."""

    __tablename__ = "tutor_notifications"
    __table_args__ = (
        UniqueConstraint(
            "kind", "ref_id", "target", "target_id", name="uq_tutor_notifications_event"
        ),
        CheckConstraint(
            "kind IN ('lesson', 'fee_due', 'fee_overdue', 'cancel', 'move', 'announce', 'manual')",
            name="ck_tutor_notifications_kind",
        ),
        CheckConstraint(
            "target IN ('student', 'group', 'owner')", name="ck_tutor_notifications_target"
        ),
        CheckConstraint(
            "status IN ('sent', 'skipped', 'failed')", name="ck_tutor_notifications_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
