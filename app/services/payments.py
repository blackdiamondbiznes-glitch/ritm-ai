"""Owner payment requests and super-admin review.

Bot buttons and the Mini App call the same methods here, so every transition is
checked and logged the same way. Each change writes one immutable PaymentEvent.
"""

import random
import re
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.db.models.payments import (
    METHOD_CARD,
    REVIEWABLE,
    STATUS_APPROVED,
    STATUS_CANCELED,
    STATUS_DISPUTED,
    STATUS_DRAFT,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Payment,
    PaymentEvent,
)
from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.payments import PaymentEventRepository, PaymentRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.clock import TASHKENT, Clock, utcnow
from app.services.pricing import is_paid_plan, paid_days, period_percent, total_amount

PAID_CODES = ("start", "pro", "agency")
REF_PREFIX = "RITM-"
REF_ALPHABET = "".join(ch for ch in string.ascii_uppercase + string.digits if ch not in "IO01")
MAX_OFFSET = 99  # so'm added to make each open request's amount unique
TRANSFER_MAX_AGE = timedelta(days=7)
TRANSFER_FUTURE_SLACK = timedelta(minutes=10)
ACTOR_OWNER = "owner"
ACTOR_ADMIN = "admin"
ACTOR_SYSTEM = "system"


@dataclass(frozen=True)
class Receipt:
    """A Telegram photo or document. `unique_id` is stable for the same file."""

    file_id: str
    unique_id: str
    kind: str = "photo"


@dataclass
class Submitted:
    """A request that reached the admin queue, plus other requests with the same receipt."""

    payment: Payment
    duplicates: list[Payment] = field(default_factory=list)


@dataclass
class FakeMarked:
    payment: Payment
    owner: User
    blocked: bool


def parse_transfer_time(raw: str, now: datetime) -> datetime | None:
    """Read HH:MM, DD.MM HH:MM or DD.MM.YYYY HH:MM in Tashkent time. None when unreadable.

    A bare time later than now (plus slack) is taken as yesterday.
    """
    text = (raw or "").strip().replace("/", ".").replace("-", ".")
    local_now = now.astimezone(TASHKENT)
    match = re.fullmatch(r"(?:(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s+)?(\d{1,2})[:.](\d{2})", text)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    try:
        if day is None:
            moment = local_now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if moment - local_now > TRANSFER_FUTURE_SLACK:
                moment -= timedelta(days=1)
        else:
            full_year = int(year) if year else local_now.year
            if full_year < 100:
                full_year += 2000
            moment = local_now.replace(
                year=full_year,
                month=int(month),
                day=int(day),
                hour=int(hour),
                minute=int(minute),
                second=0,
                microsecond=0,
            )
    except ValueError:
        return None
    return moment.astimezone(now.tzinfo or TASHKENT)


@dataclass(frozen=True)
class Quote:
    """What the owner would pay for one plan and period."""

    plan: Plan
    months: int
    monthly: int
    amount: int
    founder: bool
    list_total: int = 0
    period_percent: int = 0

    @property
    def savings(self) -> int:
        return max(0, self.list_total - self.amount)

    @property
    def monthly_equivalent(self) -> int:
        if self.months <= 0:
            return self.amount
        return self.amount // self.months


class PaymentError(Exception):
    """A user-facing payment outcome represented by a locale key suffix."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PaymentService:
    """Create pending requests and apply a reviewed payment once."""

    def __init__(
        self,
        payments: PaymentRepository,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        users: UserRepository,
        access: AccessService,
        audit: AuditRepository,
        now: Clock | None = None,
        discounts: dict[int, int] | None = None,
        events: PaymentEventRepository | None = None,
        *,
        terms_version: str = "2026-11-v1",
        draft_ttl_hours: int = 24,
        fake_block_after: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self._payments = payments
        self._plans = plans
        self._subs = subscriptions
        self._users = users
        self._access = access
        self._audit = audit
        self._now = now or utcnow
        self._discounts = discounts or {}
        self._events = events
        self.terms_version = terms_version
        self._draft_ttl = timedelta(hours=max(1, draft_ttl_hours))
        self._fake_block_after = max(1, fake_block_after)
        self._rng = rng or random.SystemRandom()

    async def quote(self, owner: User, plan_code: str, months: int) -> Quote:
        """Price a request. Raises PaymentError on a bad plan or period."""
        plan = await self._plans.get_by_code(plan_code)
        if plan is None or not is_paid_plan(plan):
            raise PaymentError("plan")
        founder = await self._access.offers_founder_price(owner)
        monthly = self._access.unit_price(plan, founder=founder)
        percent = period_percent(months, self._discounts)
        try:
            amount = total_amount(monthly, months, percent)
        except ValueError as exc:
            raise PaymentError("months") from exc
        return Quote(plan, months, monthly, amount, founder, monthly * months, percent)

    def now(self) -> datetime:
        return self._now()

    async def plan_of(self, payment: Payment) -> Plan | None:
        return await self._plans.get_by_id(payment.plan_id)

    async def pending_of(self, owner_id: int) -> Payment | None:
        """The owner's request waiting for review (pending or disputed)."""
        return await self._payments.get_pending(owner_id)

    async def draft_of(self, owner: User) -> Payment | None:
        """The owner's issued reference that has not been submitted yet (expired ones closed)."""
        draft = await self._payments.get_draft(owner.id)
        if draft is not None and await self._expire_if_stale(draft):
            return None
        return draft

    async def start(
        self, owner: User, plan_code: str, months: int, *, terms_version: str | None
    ) -> Payment:
        """Accept the terms and issue a reference code plus an exact amount to transfer.

        Re-opening the same plan and period returns the same draft, so the code and
        amount the owner may already have typed into the bank app stay valid.
        """
        if owner.payments_blocked:
            raise PaymentError("blocked")
        if not terms_version or terms_version != self.terms_version:
            raise PaymentError("terms")
        if await self._payments.get_pending(owner.id) is not None:
            raise PaymentError("duplicate")
        quote = await self.quote(owner, plan_code, months)
        await self._payments.lock_amounts()
        draft = await self.draft_of(owner)
        if draft is not None:
            same = (
                draft.plan_id == quote.plan.id
                and draft.requested_period_months == quote.months
                and draft.base_amount_uzs == quote.amount
                and draft.terms_version == terms_version
            )
            if same:
                return draft
            await self._move(draft, STATUS_CANCELED, owner, ACTOR_OWNER, "replaced", {})
        now = self._now()
        payment = Payment(
            owner_id=owner.id,
            plan_id=quote.plan.id,
            base_amount_uzs=quote.amount,
            amount_uzs=await self._unique_amount(quote.amount),
            method=METHOD_CARD,
            status=STATUS_DRAFT,
            requested_period_months=quote.months,
            ref_code=await self._new_ref(),
            terms_version=terms_version,
            terms_accepted_at=now,
        )
        await self._payments.add(payment)
        await self._log(
            payment,
            owner,
            ACTOR_OWNER,
            "created",
            None,
            STATUS_DRAFT,
            {
                "plan": quote.plan.code,
                "months": quote.months,
                "base_amount": quote.amount,
                "amount": payment.amount_uzs,
                "ref": payment.ref_code,
                "terms_version": terms_version,
                "terms_accepted_at": now.isoformat(),
                "founder": quote.founder,
            },
        )
        return payment

    async def submit(
        self,
        owner: User,
        payment_id: int,
        *,
        receipt: Receipt | None,
        card_last4: str | None,
        transfer_at: datetime | None,
    ) -> Submitted:
        """Send a draft to the admin queue. Receipt, card last 4 and transfer time are required."""
        payment = await self._payments.get(payment_id)
        if payment is None or payment.owner_id != owner.id:
            raise PaymentError("missing")
        if payment.status == STATUS_DRAFT and await self._expire_if_stale(payment):
            raise PaymentError("expired")
        if payment.status != STATUS_DRAFT:
            raise PaymentError("status")
        if owner.payments_blocked:
            raise PaymentError("blocked")
        if receipt is None or not receipt.file_id or not receipt.unique_id:
            raise PaymentError("receipt")
        last4 = (card_last4 or "").strip()
        if not re.fullmatch(r"\d{4}", last4):
            raise PaymentError("last4")
        now = self._now()
        if transfer_at is None or not (
            now - TRANSFER_MAX_AGE <= transfer_at <= now + TRANSFER_FUTURE_SLACK
        ):
            raise PaymentError("when")
        if await self._payments.get_pending(owner.id) is not None:
            raise PaymentError("duplicate")
        duplicates = await self._payments.with_receipt(receipt.unique_id, payment.id)
        payment.receipt_file_id = receipt.file_id
        payment.receipt_unique_id = receipt.unique_id
        payment.receipt_kind = receipt.kind
        payment.payer_card_last4 = last4
        payment.transfer_at = transfer_at
        payment.submitted_at = now
        payment.duplicate_of_id = duplicates[0].id if duplicates else None
        await self._move(
            payment,
            STATUS_PENDING,
            owner,
            ACTOR_OWNER,
            "submitted",
            {
                "card_last4": last4,
                "transfer_at": transfer_at.isoformat(),
                "receipt_kind": receipt.kind,
                "receipt_file_id": receipt.file_id,
            },
            receipt_unique_id=receipt.unique_id,
        )
        if duplicates:
            await self._log(
                payment,
                None,
                ACTOR_SYSTEM,
                "duplicate_receipt",
                STATUS_PENDING,
                STATUS_PENDING,
                {"also_used_by": [row.id for row in duplicates]},
                receipt_unique_id=receipt.unique_id,
            )
        return Submitted(payment, duplicates)

    async def cancel_pending(self, owner: User) -> bool:
        """Owner drops their draft or unreviewed request. Returns False when none is open."""
        payment = await self._payments.get_pending(owner.id) or await self._payments.get_draft(
            owner.id
        )
        if payment is None or payment.status == STATUS_DISPUTED:
            return False
        payment.reject_reason = "canceled"
        payment.reviewed_at = self._now()
        await self._move(payment, STATUS_CANCELED, owner, ACTOR_OWNER, "canceled", {})
        return True

    async def get(self, payment_id: int) -> Payment | None:
        """Load one payment for the admin review screen."""
        return await self._payments.get(payment_id)

    async def list_pending(self) -> list[Payment]:
        """Admin queue (pending and disputed), oldest first."""
        return await self._payments.list_pending()

    async def duplicates_of(self, payment: Payment) -> list[Payment]:
        """Other requests that used the same receipt file."""
        if not payment.receipt_unique_id:
            return []
        return await self._payments.with_receipt(payment.receipt_unique_id, payment.id)

    async def history(self, payment_id: int) -> list[PaymentEvent]:
        if self._events is None:
            return []
        return await self._events.for_payment(payment_id)

    async def approve(self, reviewer: User, payment_id: int, *, via: str = "bot") -> Payment:
        """Activate or extend the plan. A second approve is a no-op."""
        payment = await self._require_locked(payment_id)
        if payment.status == STATUS_APPROVED:
            return payment
        if payment.status not in REVIEWABLE:
            raise PaymentError("status")
        plan = await self._plans.get_by_id(payment.plan_id)
        if plan is None:
            raise PaymentError("plan")
        owner = await self._users.get_by_id(payment.owner_id)
        if owner is None:
            raise PaymentError("owner")
        await self._payments.lock_founder_slots()
        founder = await self._access.grant_founder(owner)
        monthly = self._access.unit_price(plan, founder=founder)
        await self._apply_subscription(owner, plan, payment, monthly)
        payment.reviewed_by = reviewer.id
        payment.reviewed_at = self._now()
        until = await self.owner_expiry(owner.id)
        await self._move(
            payment,
            STATUS_APPROVED,
            reviewer,
            ACTOR_ADMIN,
            "approved",
            {
                "via": via,
                "owner_id": owner.id,
                "plan": plan.code,
                "founder": founder,
                "until": until.isoformat() if until else None,
            },
        )
        return payment

    async def reject(
        self, reviewer: User, payment_id: int, reason: str, *, via: str = "bot"
    ) -> Payment:
        """Refuse an open request. A reason is required and is shown to the owner."""
        text = (reason or "").strip()[:500]
        if not text:
            raise PaymentError("reason")
        payment = await self._require_locked(payment_id)
        if payment.status not in REVIEWABLE:
            raise PaymentError("status")
        payment.reject_reason = text
        payment.reviewed_by = reviewer.id
        payment.reviewed_at = self._now()
        await self._move(
            payment,
            STATUS_REJECTED,
            reviewer,
            ACTOR_ADMIN,
            "rejected",
            {"reason": text, "via": via},
        )
        return payment

    async def mark_fake(
        self, reviewer: User, payment_id: int, note: str = "", *, via: str = "bot"
    ) -> FakeMarked:
        """Reject as a fake receipt and count it against the owner; block after repeats."""
        payment = await self._require_locked(payment_id)
        if payment.is_fake or payment.status not in (*REVIEWABLE, STATUS_REJECTED):
            raise PaymentError("status")
        owner = await self._users.get_by_id(payment.owner_id)
        if owner is None:
            raise PaymentError("owner")
        text = (note or "").strip()[:500] or "fake_receipt"
        before = payment.status
        payment.is_fake = True
        payment.reject_reason = text
        payment.reviewed_by = reviewer.id
        payment.reviewed_at = self._now()
        owner.fake_receipts = int(owner.fake_receipts or 0) + 1
        blocked = owner.fake_receipts >= self._fake_block_after
        if blocked:
            owner.payments_blocked = True
        payment.status = STATUS_REJECTED
        await self._log(
            payment,
            reviewer,
            ACTOR_ADMIN,
            "marked_fake",
            before,
            STATUS_REJECTED,
            {"note": text, "via": via, "fake_count": owner.fake_receipts, "blocked": blocked},
            receipt_unique_id=payment.receipt_unique_id,
        )
        return FakeMarked(payment, owner, blocked)

    async def dispute(self, owner: User, payment_id: int, text: str) -> Payment:
        """Owner objects to a rejection once. The request goes back to the admin queue."""
        payment = await self._payments.get(payment_id)
        if payment is None or payment.owner_id != owner.id:
            raise PaymentError("missing")
        if payment.is_fake:
            raise PaymentError("fake")
        if payment.status != STATUS_REJECTED or payment.reject_reason == "canceled":
            raise PaymentError("status")
        if payment.disputed_at is not None:
            raise PaymentError("once")
        comment = (text or "").strip()[:1000]
        if not comment:
            raise PaymentError("reason")
        payment.dispute_text = comment
        payment.disputed_at = self._now()
        await self._move(
            payment, STATUS_DISPUTED, owner, ACTOR_OWNER, "disputed", {"text": comment}
        )
        return payment

    async def set_payments_blocked(
        self, actor: User, target: User, blocked: bool, reason: str
    ) -> User:
        """Super admin lifts or sets the payment block. Reason required, audited."""
        text = (reason or "").strip()[:500]
        if not text:
            raise PaymentError("reason")
        target.payments_blocked = blocked
        if not blocked:
            target.fake_receipts = 0
        await self._audit.add(
            actor_user_id=actor.id,
            action="payments_blocked" if blocked else "payments_unblocked",
            entity="user",
            entity_id=str(target.id),
            data={"reason": text, "telegram_id": target.telegram_id},
        )
        return target

    async def _expire_if_stale(self, draft: Payment) -> bool:
        created = draft.created_at
        if created is None or self._now() - created < self._draft_ttl:
            return False
        await self._move(draft, STATUS_EXPIRED, None, ACTOR_SYSTEM, "expired", {})
        return True

    async def _new_ref(self) -> str:
        for size in (4, 4, 4, 4, 4, 5, 5, 5, 6, 6):
            ref = REF_PREFIX + "".join(self._rng.choice(REF_ALPHABET) for _ in range(size))
            if not await self._payments.ref_exists(ref):
                return ref
        raise PaymentError("busy")

    async def _unique_amount(self, base: int) -> int:
        used = await self._payments.amounts_in_use(base)
        free = [base + offset for offset in range(1, MAX_OFFSET + 1) if base + offset not in used]
        if not free:
            raise PaymentError("busy")
        return self._rng.choice(free)

    async def _move(
        self,
        payment: Payment,
        to_status: str,
        actor: User | None,
        kind: str,
        action: str,
        data: dict,
        *,
        receipt_unique_id: str | None = None,
    ) -> None:
        before = payment.status
        payment.status = to_status
        await self._log(
            payment,
            actor,
            kind,
            action,
            before,
            to_status,
            data,
            receipt_unique_id=receipt_unique_id,
        )

    async def _log(
        self,
        payment: Payment,
        actor: User | None,
        kind: str,
        action: str,
        before: str | None,
        after: str | None,
        data: dict,
        *,
        receipt_unique_id: str | None = None,
    ) -> None:
        if self._events is None:
            await self._audit.add(
                actor_user_id=actor.id if actor else None,
                action=f"payment_{action}",
                entity="payment",
                entity_id=str(payment.id),
                data=data,
            )
            return
        await self._events.add(
            PaymentEvent(
                payment_id=payment.id,
                actor_user_id=actor.id if actor else None,
                actor_kind=kind,
                action=action,
                from_status=before,
                to_status=after,
                receipt_unique_id=receipt_unique_id,
                data=data,
            )
        )

    async def _apply_subscription(
        self, owner: User, plan: Plan, payment: Payment, monthly: int
    ) -> None:
        now = self._now()
        days = paid_days(payment.requested_period_months)
        open_sub = await self._subs.get_open(owner.id)
        if open_sub is not None and open_sub.plan_id == plan.id and open_sub.expires_at > now:
            open_sub.expires_at = open_sub.expires_at + timedelta(days=days)
            open_sub.status = SubscriptionStatus.ACTIVE
            open_sub.source = SubscriptionSource.MANUAL_PAYMENT
            open_sub.price_uzs = monthly
            open_sub.paid_amount_uzs = payment.amount_uzs
            return
        if open_sub is not None:
            open_sub.status = SubscriptionStatus.EXPIRED
        await self._subs.add(
            Subscription(
                owner_id=owner.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.MANUAL_PAYMENT,
                started_at=now,
                expires_at=now + timedelta(days=days),
                price_uzs=monthly,
                paid_amount_uzs=payment.amount_uzs,
            )
        )

    async def owner_expiry(self, owner_id: int):
        """Current paid or trial end, if the owner still has an open subscription."""
        sub = await self._subs.get_open(owner_id)
        return None if sub is None else sub.expires_at

    async def _require_locked(self, payment_id: int) -> Payment:
        """Row-locked load so concurrent reviews of one request apply once."""
        payment = await self._payments.get_for_update(payment_id)
        if payment is None:
            raise PaymentError("missing")
        return payment

    async def _require(self, payment_id: int) -> Payment:
        payment = await self._payments.get(payment_id)
        if payment is None:
            raise PaymentError("missing")
        return payment
