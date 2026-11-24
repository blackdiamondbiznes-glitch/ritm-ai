"""Subscriptions. At most one open (trial or active) row per owner."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionStatus(str, enum.Enum):
    """Lifecycle of a subscription row."""

    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


class SubscriptionSource(str, enum.Enum):
    """How the subscription was created."""

    TRIAL = "trial"
    MANUAL_PAYMENT = "manual_payment"
    ADMIN_GRANT = "admin_grant"


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class Subscription(Base):
    """A time-bounded plan assignment for one owner."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_owner_id", "owner_id"),
        Index("ix_subscriptions_workspace_id", "workspace_id"),
        Index("ix_subscriptions_plan_id", "plan_id"),
        Index("ix_subscriptions_status", "status"),
        Index(
            "uq_subscriptions_one_open_legacy",
            "owner_id",
            unique=True,
            postgresql_where=text("status IN ('trial', 'active') AND workspace_id IS NULL"),
        ),
        Index(
            "uq_subscriptions_one_open_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status IN ('trial', 'active') AND workspace_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_status",
            native_enum=True,
            values_callable=_values,
        ),
        nullable=False,
    )
    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(
            SubscriptionSource,
            name="subscription_source",
            native_enum=True,
            values_callable=_values,
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_uzs: Mapped[int | None] = mapped_column(Integer)
    paid_amount_uzs: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
