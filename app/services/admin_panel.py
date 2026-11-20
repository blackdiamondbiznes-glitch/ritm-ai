"""Read models for the super-admin Mini App panel. Only real recorded data.

Mutations (approve, reject, grant...) live in PaymentService and AdminService;
this module only reads and shapes rows for JSON.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog
from app.db.models.chats import Chat
from app.db.models.jobs import Job, JobStatus
from app.db.models.payments import OPEN_STATUSES, Payment, PaymentEvent
from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.usage import UsageCounter
from app.db.models.users import User
from app.services.clock import TASHKENT, Clock, utcnow

LIST_LIMIT = 50


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Current calendar month in Tashkent, as aware datetimes."""
    local = now.astimezone(TASHKENT)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "name": user.full_name,
        "username": user.username,
    }


def payment_row(payment: Payment, owner: User | None, plan: Plan | None) -> dict[str, Any]:
    return {
        "id": payment.id,
        "ref": payment.ref_code,
        "status": payment.status,
        "amount_uzs": payment.amount_uzs,
        "base_amount_uzs": payment.base_amount_uzs,
        "months": payment.requested_period_months,
        "plan": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "owner": user_brief(owner),
        "card_last4": payment.payer_card_last4,
        "transfer_at": iso(payment.transfer_at),
        "submitted_at": iso(payment.submitted_at),
        "created_at": iso(payment.created_at),
        "reviewed_at": iso(payment.reviewed_at),
        "has_receipt": bool(payment.receipt_file_id),
        "receipt_kind": payment.receipt_kind,
        "duplicate_of": payment.duplicate_of_id,
        "is_fake": bool(payment.is_fake),
        "reject_reason": payment.reject_reason,
        "dispute_text": payment.dispute_text,
        "disputed_at": iso(payment.disputed_at),
        "terms_version": payment.terms_version,
        "terms_accepted_at": iso(payment.terms_accepted_at),
    }


class AdminPanel:
    """Queries for overview, tenants, payments, chats and the audit trail."""

    def __init__(
        self, session: AsyncSession, *, founder_slots: int, now: Clock | None = None
    ) -> None:
        self._s = session
        self._slots = founder_slots
        self._now = now or utcnow

    async def overview(self) -> dict[str, Any]:
        now = self._now()
        start, end = month_bounds(now)
        s = self._s
        tenants = await s.scalar(select(func.count(func.distinct(Chat.owner_id))))
        users = await s.scalar(select(func.count()).select_from(User))
        chats_active = await s.scalar(
            select(func.count()).select_from(Chat).where(Chat.is_active.is_(True))
        )
        by_plan_rows = (
            await s.execute(
                select(Plan.code, Plan.name, func.count())
                .join(Subscription, Subscription.plan_id == Plan.id)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at > now,
                )
                .group_by(Plan.code, Plan.name, Plan.sort_order)
                .order_by(Plan.sort_order)
            )
        ).all()
        trials = await s.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SubscriptionStatus.TRIAL, Subscription.expires_at > now)
        )
        mrr = await s.scalar(
            select(func.coalesce(func.sum(Subscription.price_uzs), 0)).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.source == SubscriptionSource.MANUAL_PAYMENT,
                Subscription.expires_at > now,
            )
        )
        revenue, revenue_count = (
            await s.execute(
                select(func.coalesce(func.sum(Payment.amount_uzs), 0), func.count()).where(
                    Payment.status == "approved",
                    Payment.reviewed_at >= start,
                    Payment.reviewed_at < end,
                )
            )
        ).one()
        statuses = dict(
            (await s.execute(select(Payment.status, func.count()).group_by(Payment.status))).all()
        )
        founders = await s.scalar(
            select(func.count()).select_from(User).where(User.is_founder.is_(True))
        )
        since = now - timedelta(hours=24)
        failed = await s.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.FAILED, Job.finished_at >= since)
        )
        retrying = await s.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.PENDING, Job.attempts > 0, Job.last_error.is_not(None))
        )
        period = now.strftime("%Y-%m")
        ai_used, ai_owners = (
            await s.execute(
                select(func.coalesce(func.sum(UsageCounter.count), 0), func.count()).where(
                    UsageCounter.period_key == period
                )
            )
        ).one()
        blocked = await s.scalar(
            select(func.count()).select_from(User).where(User.payments_blocked.is_(True))
        )
        return {
            "tenants": int(tenants or 0),
            "users": int(users or 0),
            "chats_active": int(chats_active or 0),
            "active_by_plan": [
                {"plan": code, "name": name, "count": int(n)} for code, name, n in by_plan_rows
            ],
            "active_total": sum(int(n) for _c, _n, n in by_plan_rows),
            "trials": int(trials or 0),
            "mrr_uzs": int(mrr or 0),
            "revenue_month_uzs": int(revenue or 0),
            "revenue_month_count": int(revenue_count or 0),
            "month": start.strftime("%Y-%m"),
            "founder_used": int(founders or 0),
            "founder_slots": self._slots,
            "founder_left": max(0, self._slots - int(founders or 0)),
            "payments_pending": int(statuses.get("pending", 0)),
            "payments_disputed": int(statuses.get("disputed", 0)),
            "payments_blocked_users": int(blocked or 0),
            "jobs_failed_24h": int(failed or 0),
            "jobs_retrying": int(retrying or 0),
            "ai_used_month": int(ai_used or 0),
            "ai_owners_month": int(ai_owners or 0),
        }

    async def tenants(self, query: str = "") -> list[dict[str, Any]]:
        """Owners: anyone with a chat, a subscription or a payment. Newest activity first."""
        owner_ids = (
            select(Chat.owner_id.label("uid"))
            .union(select(Subscription.owner_id), select(Payment.owner_id))
            .subquery()
        )
        stmt = select(User).where(User.id.in_(select(owner_ids.c.uid)))
        text = (query or "").strip()
        if text:
            like = f"%{text.lstrip('@')}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(like),
                    User.username.ilike(like),
                    cast(User.telegram_id, String).like(f"%{text}%"),
                )
            )
        stmt = stmt.order_by(User.last_seen_at.desc().nullslast(), User.id.desc()).limit(LIST_LIMIT)
        users = list((await self._s.execute(stmt)).scalars().all())
        if not users:
            return []
        ids = [user.id for user in users]
        chats = dict(
            (
                await self._s.execute(
                    select(Chat.owner_id, func.count())
                    .where(Chat.owner_id.in_(ids), Chat.is_active.is_(True))
                    .group_by(Chat.owner_id)
                )
            ).all()
        )
        subs = await self._open_subs(ids)
        rows = []
        for user in users:
            sub = subs.get(user.id)
            rows.append(
                {
                    **user_brief(user),
                    "chats": int(chats.get(user.id, 0)),
                    "plan": sub["plan"] if sub else "free",
                    "plan_name": sub["plan_name"] if sub else "Free",
                    "sub_status": sub["status"] if sub else None,
                    "expires_at": sub["expires_at"] if sub else None,
                    "is_founder": bool(user.is_founder),
                    "fake_receipts": int(user.fake_receipts or 0),
                    "payments_blocked": bool(user.payments_blocked),
                    "is_blocked": bool(user.is_blocked),
                    "last_seen_at": iso(user.last_seen_at),
                }
            )
        return rows

    async def tenant(self, user_id: int) -> dict[str, Any] | None:
        user = await self._s.get(User, user_id)
        if user is None:
            return None
        chats = (
            (
                await self._s.execute(
                    select(Chat).where(Chat.owner_id == user.id).order_by(Chat.id.desc())
                )
            )
            .scalars()
            .all()
        )
        subs = (
            await self._s.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.owner_id == user.id)
                .order_by(Subscription.id.desc())
                .limit(10)
            )
        ).all()
        pays = await self._payments(Payment.owner_id == user.id, limit=30)
        period = self._now().strftime("%Y-%m")
        used = await self._s.scalar(
            select(func.coalesce(func.sum(UsageCounter.count), 0)).where(
                UsageCounter.owner_id == user.id, UsageCounter.period_key == period
            )
        )
        audit = await self._audit_rows(
            or_(
                AuditLog.actor_user_id == user.id,
                (AuditLog.entity == "user") & (AuditLog.entity_id == str(user.id)),
                (AuditLog.entity == "subscription")
                & AuditLog.entity_id.in_([str(sub.id) for sub, _plan in subs] or ["-"]),
            ),
            limit=20,
        )
        open_sub = next(
            (
                (sub, plan)
                for sub, plan in subs
                if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)
            ),
            None,
        )
        return {
            "user": {
                **user_brief(user),
                "language": user.language_code,
                "is_founder": bool(user.is_founder),
                "founder_since": iso(user.founder_since),
                "fake_receipts": int(user.fake_receipts or 0),
                "payments_blocked": bool(user.payments_blocked),
                "is_blocked": bool(user.is_blocked),
                "created_at": iso(user.created_at),
                "last_seen_at": iso(user.last_seen_at),
            },
            "plan": {
                "code": open_sub[1].code if open_sub else "free",
                "name": open_sub[1].name if open_sub else "Free",
                "status": open_sub[0].status.value if open_sub else None,
                "expires_at": iso(open_sub[0].expires_at) if open_sub else None,
                "ai_used": int(used or 0),
                "ai_limit": open_sub[1].ai_generations_per_month if open_sub else None,
                "max_chats": open_sub[1].max_chats if open_sub else None,
            },
            "chats": [self._chat_row(chat, user) for chat in chats],
            "subscriptions": [
                {
                    "id": sub.id,
                    "plan": plan.code,
                    "plan_name": plan.name,
                    "status": sub.status.value,
                    "source": sub.source.value,
                    "started_at": iso(sub.started_at),
                    "expires_at": iso(sub.expires_at),
                    "paid_amount_uzs": sub.paid_amount_uzs,
                }
                for sub, plan in subs
            ],
            "payments": pays,
            "audit": audit,
        }

    async def payments(self, status: str = "queue") -> list[dict[str, Any]]:
        if status == "queue":
            cond = Payment.status.in_(OPEN_STATUSES)
            return await self._payments(cond, oldest_first=True)
        if status == "disputes":
            return await self._payments(Payment.disputed_at.is_not(None))
        if status == "fake":
            return await self._payments(Payment.is_fake.is_(True))
        if status in ("approved", "rejected", "draft", "canceled", "expired"):
            return await self._payments(Payment.status == status)
        return await self._payments(Payment.status != "draft")

    async def payment(self, payment_id: int) -> dict[str, Any] | None:
        rows = await self._payments(Payment.id == payment_id, limit=1)
        if not rows:
            return None
        data = rows[0]
        events = (
            (
                await self._s.execute(
                    select(PaymentEvent)
                    .where(PaymentEvent.payment_id == payment_id)
                    .order_by(PaymentEvent.id)
                )
            )
            .scalars()
            .all()
        )
        actors = await self._users([e.actor_user_id for e in events if e.actor_user_id])
        data["events"] = [self._event_row(event, actors) for event in events]
        payment = await self._s.get(Payment, payment_id)
        dups: list[dict[str, Any]] = []
        if payment is not None and payment.receipt_unique_id:
            dups = await self._payments(
                (Payment.receipt_unique_id == payment.receipt_unique_id)
                & (Payment.id != payment_id)
            )
        data["duplicates"] = dups
        owner_id = payment.owner_id if payment else None
        owner = await self._s.get(User, owner_id) if owner_id else None
        data["owner_flags"] = {
            "fake_receipts": int(owner.fake_receipts or 0) if owner else 0,
            "payments_blocked": bool(owner.payments_blocked) if owner else False,
        }
        return data

    async def chats(self, query: str = "") -> list[dict[str, Any]]:
        stmt = select(Chat)
        text = (query or "").strip()
        if text:
            stmt = stmt.where(
                or_(
                    Chat.title.ilike(f"%{text}%"),
                    Chat.username.ilike(f"%{text.lstrip('@')}%"),
                    cast(Chat.telegram_chat_id, String).like(f"%{text}%"),
                )
            )
        stmt = stmt.order_by(Chat.is_active.desc(), Chat.id.desc()).limit(100)
        chats = list((await self._s.execute(stmt)).scalars().all())
        owners = await self._users([chat.owner_id for chat in chats])
        return [self._chat_row(chat, owners.get(chat.owner_id)) for chat in chats]

    async def audit(self, limit: int = 100) -> list[dict[str, Any]]:
        """Payment events and other audit rows, newest first."""
        events = (
            (
                await self._s.execute(
                    select(PaymentEvent).order_by(PaymentEvent.id.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        actors = await self._users([e.actor_user_id for e in events if e.actor_user_id])
        rows = [self._event_row(event, actors) for event in events]
        rows += await self._audit_rows(None, limit=limit)
        rows.sort(key=lambda row: row["created_at"] or "", reverse=True)
        return rows[:limit]

    async def _payments(
        self, condition, *, limit: int = LIST_LIMIT, oldest_first: bool = False
    ) -> list[dict[str, Any]]:
        order = (Payment.created_at, Payment.id) if oldest_first else (Payment.id.desc(),)
        stmt = (
            select(Payment, User, Plan)
            .join(User, User.id == Payment.owner_id)
            .join(Plan, Plan.id == Payment.plan_id)
            .where(condition)
            .order_by(*order)
            .limit(limit)
        )
        return [payment_row(p, u, pl) for p, u, pl in (await self._s.execute(stmt)).all()]

    async def _open_subs(self, ids: list[int]) -> dict[int, dict[str, Any]]:
        now = self._now()
        rows = (
            await self._s.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.owner_id.in_(ids),
                    Subscription.status.in_((SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)),
                )
            )
        ).all()
        out = {}
        for sub, plan in rows:
            live = sub.expires_at > now
            out[sub.owner_id] = {
                "plan": plan.code if live else "free",
                "plan_name": plan.name if live else "Free",
                "status": sub.status.value if live else "expired",
                "expires_at": iso(sub.expires_at),
            }
        return out

    async def _users(self, ids: list[int]) -> dict[int, User]:
        unique = sorted({i for i in ids if i})
        if not unique:
            return {}
        rows = (await self._s.execute(select(User).where(User.id.in_(unique)))).scalars().all()
        return {user.id: user for user in rows}

    async def _audit_rows(self, condition, *, limit: int) -> list[dict[str, Any]]:
        stmt = select(AuditLog)
        if condition is not None:
            stmt = stmt.where(condition)
        rows = (
            (await self._s.execute(stmt.order_by(AuditLog.id.desc()).limit(limit))).scalars().all()
        )
        actors = await self._users([row.actor_user_id for row in rows if row.actor_user_id])
        return [
            {
                "kind": "audit",
                "id": row.id,
                "action": row.action,
                "entity": row.entity,
                "entity_id": row.entity_id,
                "actor": user_brief(actors.get(row.actor_user_id)),
                "data": row.data,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]

    @staticmethod
    def _event_row(event: PaymentEvent, actors: dict[int, User]) -> dict[str, Any]:
        return {
            "kind": "payment",
            "id": event.id,
            "payment_id": event.payment_id,
            "action": event.action,
            "actor_kind": event.actor_kind,
            "actor": user_brief(actors.get(event.actor_user_id)),
            "from_status": event.from_status,
            "to_status": event.to_status,
            "data": event.data,
            "created_at": iso(event.created_at),
        }

    @staticmethod
    def _chat_row(chat: Chat, owner: User | None) -> dict[str, Any]:
        return {
            "id": chat.id,
            "telegram_chat_id": chat.telegram_chat_id,
            "title": chat.title,
            "username": chat.username,
            "type": chat.type.value if hasattr(chat.type, "value") else str(chat.type),
            "is_active": bool(chat.is_active),
            "added_at": iso(chat.added_at),
            "removed_at": iso(chat.removed_at),
            "owner": user_brief(owner),
        }
