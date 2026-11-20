"""Payment quotes, pending dedup, approve extend/restart, and reject."""

from datetime import UTC, datetime, timedelta

from app.db.models.payments import STATUS_APPROVED, STATUS_PENDING, STATUS_REJECTED, Payment
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.services.access import AccessService
from app.services.payments import PaymentError, PaymentService, Receipt
from app.services.pricing import round_soum, total_amount
from tests.fakes import (
    FakeAudit,
    FakeChats,
    FakePlans,
    FakeSubs,
    FakeUsage,
    FakeUsers,
    make_plans,
    make_user,
)

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)


class _Payments:
    def __init__(self) -> None:
        self.rows: list[Payment] = []
        self._seq = 0

    async def add(self, payment: Payment) -> Payment:
        self._seq += 1
        payment.id = self._seq
        payment.created_at = NOW
        self.rows.append(payment)
        return payment

    async def get(self, payment_id: int) -> Payment | None:
        return next((row for row in self.rows if row.id == payment_id), None)

    async def get_for_update(self, payment_id: int) -> Payment | None:
        return await self.get(payment_id)

    async def get_pending(self, owner_id: int) -> Payment | None:
        found = [
            row
            for row in self.rows
            if row.owner_id == owner_id and row.status in (STATUS_PENDING, "disputed")
        ]
        return found[-1] if found else None

    async def get_draft(self, owner_id: int) -> Payment | None:
        found = [row for row in self.rows if row.owner_id == owner_id and row.status == "draft"]
        return found[-1] if found else None

    async def ref_exists(self, ref: str) -> bool:
        return any(row.ref_code == ref for row in self.rows)

    async def amounts_in_use(self, base: int) -> set[int]:
        return {
            row.amount_uzs
            for row in self.rows
            if row.base_amount_uzs == base and row.status in ("draft", STATUS_PENDING, "disputed")
        }

    async def with_receipt(self, unique_id: str, exclude_id: int) -> list[Payment]:
        return [r for r in self.rows if r.receipt_unique_id == unique_id and r.id != exclude_id]

    async def lock_amounts(self) -> None:
        return None

    async def list_pending(self, limit: int = 20) -> list[Payment]:
        return [row for row in self.rows if row.status == STATUS_PENDING][:limit]

    async def lock_founder_slots(self) -> None:
        return None


def _service(
    slots: int = 20, users=None, subs=None
) -> tuple[PaymentService, _Payments, FakeSubs, FakeUsers]:
    plans = FakePlans(make_plans())
    for plan in plans._plans:  # noqa: SLF001
        regular = {"free": 0, "start": 29000, "pro": 39000, "agency": 69000}
        founder = {"free": 0, "start": 20300, "pro": 27300, "agency": 48300}
        plan.price_uzs = regular[plan.code]
        plan.founder_price_uzs = founder[plan.code]
    users = users or FakeUsers([make_user(), make_user(2, 200)])
    subs = subs or FakeSubs()
    payments = _Payments()
    access = AccessService(
        plans, subs, FakeChats(), FakeUsage(), users, now=lambda: NOW, founder_slots=slots
    )
    service = PaymentService(
        payments,
        plans,
        subs,
        users,
        access,
        FakeAudit(),
        now=lambda: NOW,
        discounts={3: 7, 12: 15},
    )
    return service, payments, subs, users


async def _pay(service: PaymentService, owner, code: str, months: int) -> Payment:
    """Accept the terms, then submit full evidence, like the bot flow does."""
    draft = await service.start(owner, code, months, terms_version=service.terms_version)
    _pay.seq = getattr(_pay, "seq", 0) + 1
    result = await service.submit(
        owner,
        draft.id,
        receipt=Receipt(f"file-{_pay.seq}", f"uniq-{_pay.seq}"),
        card_last4="1234",
        transfer_at=NOW,
    )
    return result.payment


def test_amount_is_monthly_times_months_without_a_discount() -> None:
    assert total_amount(39000, 1) == 39000
    assert total_amount(39000, 3) == 117000
    assert total_amount(27300, 12) == 327600


def test_period_discount_stacks_on_the_founder_monthly_price() -> None:
    # 27 300 * 12 * 0.85 = 278 460, rounded to the nearest 100 so'm.
    assert total_amount(27300, 12, 15) == 278500
    assert total_amount(27300, 3, 7) == 76200
    assert round_soum(278460) == 278500


async def test_quote_uses_founder_price_while_slots_remain() -> None:
    service, _payments, _subs, users = _service(slots=1)
    quote = await service.quote(users.users[0], "pro", 3)
    assert quote.founder is True
    assert quote.monthly == 27300
    assert quote.list_total == 81900
    assert quote.period_percent == 7
    assert quote.amount == 76200
    year = await service.quote(users.users[0], "pro", 12)
    assert year.amount == 278500
    assert year.savings == 49100
    users.users[0].is_founder = True
    users.users[1].is_founder = True
    full = _service(slots=1, users=users)[0]
    regular = await full.quote(users.users[1], "pro", 1)
    # user 1 is already a founder, so the locked founder price still applies
    assert regular.founder is True
    assert regular.monthly == 27300
    outsider = make_user(3, 300)
    users.users.append(outsider)
    other = await full.quote(outsider, "pro", 1)
    assert other.founder is False
    assert other.monthly == 39000


async def test_duplicate_pending_request_is_blocked() -> None:
    service, payments, _subs, users = _service()
    first = await _pay(service, users.users[0], "pro", 1)
    assert first.status == STATUS_PENDING
    try:
        await _pay(service, users.users[0], "start", 1)
    except PaymentError as exc:
        assert exc.code == "duplicate"
    else:
        raise AssertionError("duplicate")
    assert len(payments.rows) == 1
    assert await service.cancel_pending(users.users[0]) is True
    second = await _pay(service, users.users[0], "start", 1)
    assert second.plan_id != first.plan_id


async def test_approve_extends_the_same_plan_and_restarts_a_different_one() -> None:
    service, _payments, subs, users = _service()
    owner = users.users[0]
    reviewer = users.users[1]
    current = Subscription(
        owner_id=owner.id,
        plan_id=3,
        status=SubscriptionStatus.TRIAL,
        source=SubscriptionSource.TRIAL,
        started_at=NOW - timedelta(days=2),
        expires_at=NOW + timedelta(days=3),
    )
    await subs.add(current)
    payment = await _pay(service, owner, "pro", 1)
    approved = await service.approve(reviewer, payment.id)
    assert approved.status == STATUS_APPROVED
    assert current.status == SubscriptionStatus.ACTIVE
    assert current.expires_at == NOW + timedelta(days=33)
    assert current.price_uzs == 27300
    assert current.paid_amount_uzs == payment.amount_uzs
    assert owner.is_founder is True
    # Buying a different plan starts a fresh paid period.
    assert await service.cancel_pending(owner) is False
    other = await _pay(service, owner, "start", 1)
    await service.approve(reviewer, other.id)
    assert current.status == SubscriptionStatus.EXPIRED
    fresh = await subs.get_open(owner.id)
    assert fresh is not None and fresh.plan_id == 2
    assert fresh.expires_at == NOW + timedelta(days=30)


async def test_reject_keeps_the_plan_and_stores_the_reason() -> None:
    service, _payments, subs, users = _service()
    owner = users.users[0]
    payment = await _pay(service, owner, "pro", 1)
    rejected = await service.reject(users.users[1], payment.id, "Chek noaniq <b>test</b>")
    assert rejected.status == STATUS_REJECTED
    assert rejected.reject_reason.endswith("test</b>")
    assert await subs.get_open(owner.id) is None
    try:
        await service.reject(users.users[1], payment.id, "again")
    except PaymentError as exc:
        assert exc.code == "status"
    else:
        raise AssertionError("status")


async def test_second_approve_is_idempotent() -> None:
    service, _payments, _subs, users = _service()
    payment = await _pay(service, users.users[0], "pro", 1)
    first = await service.approve(users.users[1], payment.id)
    again = await service.approve(users.users[1], payment.id)
    assert again is first
    assert first.status == STATUS_APPROVED


async def test_approve_records_the_discounted_total() -> None:
    service, payments, subs, users = _service()
    owner = users.users[0]
    payment = await _pay(service, owner, "pro", 12)
    assert payment.base_amount_uzs == 278500
    assert 278501 <= payment.amount_uzs <= 278599
    approved = await service.approve(users.users[1], payment.id)
    assert approved.amount_uzs == payment.amount_uzs
    open_sub = await subs.get_open(owner.id)
    assert open_sub is not None
    assert open_sub.price_uzs == 27300
    assert open_sub.paid_amount_uzs == payment.amount_uzs
