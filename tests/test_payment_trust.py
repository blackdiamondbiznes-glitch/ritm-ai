"""Payment dispute protection on real Postgres: references, exact amounts, terms,
required evidence, duplicate receipts, reasons, disputes, fake flags, expiry, and the
append-only event log. Plus migration 0010 down/up."""

import os
import random
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.models.audit import AuditLog
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.subscriptions import Subscription
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.payments import PaymentEventRepository, PaymentRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.payments import (
    PaymentError,
    PaymentService,
    Receipt,
    parse_transfer_time,
)
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
_IDS = (9600000001, 9600000002, 9600000003, 9600000009)
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
TERMS = "2026-11-v1"

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def purge(session) -> None:
    await allow_purge(session)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    pays = select(Payment.id).where(Payment.owner_id.in_(ids))
    await session.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(pays)))
    await session.execute(
        delete(AuditLog).where(
            or_(
                AuditLog.actor_user_id.in_(ids),
                (AuditLog.entity == "user")
                & AuditLog.entity_id.in_(
                    select(text("CAST(id AS TEXT)"))
                    .select_from(User)
                    .where(User.telegram_id.in_(_IDS))
                ),
            )
        )
    )
    await session.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await purge(s)
        s.add_all(
            [User(telegram_id=tg, full_name=f"T{tg % 10}", language_code="uz") for tg in _IDS]
        )
        await s.commit()
    try:
        yield sessions
    finally:
        async with sessions() as s:
            await purge(s)
            await s.commit()
        await engine.dispose()


def service(session, now=NOW, rng=None, block_after=2) -> PaymentService:
    plans = PlanRepository(session)
    subs = SubscriptionRepository(session)
    users = UserRepository(session)
    access = AccessService(
        plans,
        subs,
        ChatRepository(session),
        UsageRepository(session),
        users,
        now=lambda: now,
        founder_slots=0,
    )
    return PaymentService(
        PaymentRepository(session),
        plans,
        subs,
        users,
        access,
        AuditRepository(session),
        now=lambda: now,
        discounts={3: 7, 12: 15},
        events=PaymentEventRepository(session),
        terms_version=TERMS,
        draft_ttl_hours=24,
        fake_block_after=block_after,
        rng=rng,
    )


async def user(session, index: int) -> User:
    return await UserRepository(session).get_by_telegram_id(_IDS[index])


async def submit(svc, owner, draft, uniq="u-1", last4="4321", when=NOW - timedelta(minutes=5)):
    return await svc.submit(
        owner, draft.id, receipt=Receipt(f"f-{uniq}", uniq), card_last4=last4, transfer_at=when
    )


async def actions(session, payment_id: int) -> list[str]:
    rows = await PaymentEventRepository(session).for_payment(payment_id)
    return [row.action for row in rows]


async def raises(code: str, coro) -> None:
    with pytest.raises(PaymentError) as info:
        await coro
    assert info.value.code == code


async def test_terms_are_required_and_drafts_get_unique_ref_and_amount(db) -> None:
    async with db() as s:
        svc = service(s)
        a, b, c = await user(s, 0), await user(s, 1), await user(s, 2)
        await raises("terms", svc.start(a, "pro", 1, terms_version=None))
        await raises("terms", svc.start(a, "pro", 1, terms_version="2025-old"))
        drafts = [await svc.start(u, "pro", 1, terms_version=TERMS) for u in (a, b, c)]
        refs = [d.ref_code for d in drafts]
        assert all(re.fullmatch(r"RITM-[A-HJ-NP-Z2-9]{4}", r) for r in refs)
        assert len(set(refs)) == 3
        assert {d.base_amount_uzs for d in drafts} == {39000}
        amounts = [d.amount_uzs for d in drafts]
        assert len(set(amounts)) == 3 and all(39001 <= x <= 39099 for x in amounts)
        assert all(d.terms_version == TERMS and d.terms_accepted_at == NOW for d in drafts)
        again = await svc.start(a, "pro", 1, terms_version=TERMS)
        assert again.id == drafts[0].id and again.ref_code == refs[0]
        switched = await svc.start(a, "start", 3, terms_version=TERMS)
        assert switched.id != drafts[0].id
        assert drafts[0].status == "canceled"
        assert await actions(s, drafts[0].id) == ["created", "replaced"]
        created = (await PaymentEventRepository(s).for_payment(switched.id))[0]
        assert created.data["terms_version"] == TERMS and created.actor_kind == "owner"
        await s.commit()


async def test_ref_collisions_are_retried(db) -> None:
    async with db() as s:
        a, b = await user(s, 0), await user(s, 1)
        first = await service(s, rng=random.Random(7)).start(a, "pro", 1, terms_version=TERMS)
        # Same seed would produce the same code: the service must pick another one.
        second = await service(s, rng=random.Random(7)).start(b, "pro", 1, terms_version=TERMS)
        assert first.ref_code != second.ref_code
        assert first.amount_uzs != second.amount_uzs
        await s.commit()


async def test_submit_needs_receipt_last4_and_time(db) -> None:
    async with db() as s:
        svc = service(s)
        a, b = await user(s, 0), await user(s, 1)
        draft = await svc.start(a, "pro", 1, terms_version=TERMS)
        ok_when = NOW - timedelta(hours=1)
        await raises(
            "receipt", svc.submit(a, draft.id, receipt=None, card_last4="1234", transfer_at=ok_when)
        )
        await raises(
            "receipt",
            svc.submit(
                a, draft.id, receipt=Receipt("f", ""), card_last4="1234", transfer_at=ok_when
            ),
        )
        await raises("last4", submit(svc, a, draft, last4="12a4"))
        await raises("last4", submit(svc, a, draft, last4="12345"))
        await raises("when", submit(svc, a, draft, when=None))
        await raises("when", submit(svc, a, draft, when=NOW - timedelta(days=8)))
        await raises("when", submit(svc, a, draft, when=NOW + timedelta(hours=1)))
        await raises("missing", submit(svc, b, draft))  # someone else's draft
        done = await submit(svc, a, draft)
        p = done.payment
        assert p.status == "pending" and p.payer_card_last4 == "4321"
        assert p.receipt_unique_id == "u-1" and p.receipt_file_id == "f-u-1"
        assert p.submitted_at == NOW and done.duplicates == []
        await raises("status", submit(svc, a, draft))
        await raises("duplicate", svc.start(a, "pro", 1, terms_version=TERMS))
        assert await actions(s, p.id) == ["created", "submitted"]
        await s.commit()


async def test_duplicate_receipts_are_flagged_across_owners(db) -> None:
    async with db() as s:
        svc = service(s)
        a, b = await user(s, 0), await user(s, 1)
        first = (
            await submit(svc, a, await svc.start(a, "pro", 1, terms_version=TERMS), uniq="same")
        ).payment
        result = await submit(
            svc, b, await svc.start(b, "pro", 1, terms_version=TERMS), uniq="same"
        )
        assert [row.id for row in result.duplicates] == [first.id]
        assert result.payment.duplicate_of_id == first.id
        assert await actions(s, result.payment.id) == ["created", "submitted", "duplicate_receipt"]
        dup_event = (await PaymentEventRepository(s).for_payment(result.payment.id))[-1]
        assert dup_event.actor_kind == "system" and dup_event.data["also_used_by"] == [first.id]
        assert [p.id for p in await svc.duplicates_of(first)] == [result.payment.id]
        await s.commit()


async def test_reject_requires_reason_then_one_dispute_then_approve(db) -> None:
    async with db() as s:
        svc = service(s)
        a, admin = await user(s, 0), await user(s, 3)
        p = (await submit(svc, a, await svc.start(a, "pro", 1, terms_version=TERMS))).payment
        await raises("reason", svc.reject(admin, p.id, "   "))
        await raises("status", svc.dispute(a, p.id, "pul o'tdi"))  # not rejected yet
        await svc.reject(admin, p.id, "Pul tushmagan")
        assert p.status == "rejected" and p.reject_reason == "Pul tushmagan"
        await raises("reason", svc.dispute(a, p.id, ""))
        await svc.dispute(a, p.id, "20.11 11:55 da Uzcard'dan o'tkazdim, tranzaksiya 8842")
        assert p.status == "disputed" and p.disputed_at == NOW
        assert (await svc.pending_of(a.id)).id == p.id  # back in the queue
        assert p.id in [row.id for row in await svc.list_pending()]
        await svc.reject(admin, p.id, "Bank ko'chirmasida yo'q")
        await raises("once", svc.dispute(a, p.id, "yana"))
        # A second look can still approve a disputed request.
        p2 = (
            await submit(
                service(s), a, await svc.start(a, "pro", 1, terms_version=TERMS), uniq="u-2"
            )
        ).payment
        await svc.reject(admin, p2.id, "Summa mos emas")
        await svc.dispute(a, p2.id, "summa to'g'ri edi")
        approved = await svc.approve(admin, p2.id, via="webapp")
        assert approved.status == "approved"
        assert await actions(s, p.id) == [
            "created",
            "submitted",
            "rejected",
            "disputed",
            "rejected",
        ]
        assert await actions(s, p2.id) == [
            "created",
            "submitted",
            "rejected",
            "disputed",
            "approved",
        ]
        last = (await PaymentEventRepository(s).for_payment(p2.id))[-1]
        assert last.actor_user_id == admin.id and last.data["via"] == "webapp"
        assert last.from_status == "disputed" and last.to_status == "approved"
        await s.commit()


async def test_fake_receipts_flag_then_block(db) -> None:
    async with db() as s:
        svc = service(s, block_after=2)
        a, admin = await user(s, 0), await user(s, 3)
        p1 = (
            await submit(svc, a, await svc.start(a, "pro", 1, terms_version=TERMS), uniq="x1")
        ).payment
        first = await svc.mark_fake(admin, p1.id, "chek tahrirlangan")
        assert first.blocked is False and a.fake_receipts == 1 and not a.payments_blocked
        assert p1.status == "rejected" and p1.is_fake
        await raises("status", svc.mark_fake(admin, p1.id))
        await raises("fake", svc.dispute(a, p1.id, "men to'ladim"))
        p2 = (
            await submit(svc, a, await svc.start(a, "pro", 1, terms_version=TERMS), uniq="x2")
        ).payment
        draft3 = None
        second = await svc.mark_fake(admin, p2.id)
        assert second.blocked is True and a.payments_blocked and a.fake_receipts == 2
        await raises("blocked", svc.start(a, "pro", 1, terms_version=TERMS))
        assert draft3 is None
        assert await actions(s, p2.id) == ["created", "submitted", "marked_fake"]
        event = (await PaymentEventRepository(s).for_payment(p2.id))[-1]
        assert event.data["blocked"] is True and event.receipt_unique_id == "x2"
        await raises("reason", svc.set_payments_blocked(admin, a, False, ""))
        await svc.set_payments_blocked(admin, a, False, "Bank tasdiqladi, xato bo'lgan")
        assert not a.payments_blocked and a.fake_receipts == 0
        audit = (
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.entity == "user", AuditLog.entity_id == str(a.id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [row.action for row in audit] == ["payments_unblocked"]
        await s.commit()


async def test_blocked_owner_cannot_submit_an_existing_draft(db) -> None:
    async with db() as s:
        svc = service(s)
        a = await user(s, 0)
        draft = await svc.start(a, "pro", 1, terms_version=TERMS)
        a.payments_blocked = True
        await raises("blocked", submit(svc, a, draft))
        await s.commit()


async def test_drafts_expire_and_cancel_is_logged(db) -> None:
    async with db() as s:
        a = await user(s, 0)
        draft = await service(s).start(a, "pro", 1, terms_version=TERMS)
        await s.execute(
            text("UPDATE payments SET created_at = :t WHERE id = :i"), {"t": NOW, "i": draft.id}
        )
        await s.refresh(draft)
        later = service(s, now=NOW + timedelta(hours=25))
        await raises("expired", submit(later, a, draft, when=NOW + timedelta(hours=24, minutes=50)))
        assert draft.status == "expired"
        assert await later.draft_of(a) is None
        fresh = await later.start(a, "pro", 1, terms_version=TERMS)
        assert await later.cancel_pending(a) is True and fresh.status == "canceled"
        assert await actions(s, draft.id) == ["created", "expired"]
        assert await actions(s, fresh.id) == ["created", "canceled"]
        expired_event = (await PaymentEventRepository(s).for_payment(draft.id))[-1]
        assert expired_event.actor_kind == "system" and expired_event.actor_user_id is None
        await s.commit()


async def test_event_log_is_append_only(db) -> None:
    async with db() as s:
        a = await user(s, 0)
        draft = await service(s).start(a, "pro", 1, terms_version=TERMS)
        await s.commit()
    for statement in (
        "UPDATE payment_events SET action = 'approved' WHERE payment_id = :i",
        "DELETE FROM payment_events WHERE payment_id = :i",
    ):
        async with db() as s:
            with pytest.raises(Exception, match="append-only"):
                await s.execute(text(statement), {"i": draft.id})
            await s.rollback()
    async with db() as s:
        await AuditRepository(s).add(
            actor_user_id=a.id, action="probe", entity="user", entity_id=str(a.id), data={}
        )
        await s.commit()
    for statement in (
        "UPDATE audit_logs SET action = 'x' WHERE actor_user_id = :u",
        "DELETE FROM audit_logs WHERE actor_user_id = :u",
    ):
        async with db() as s:
            with pytest.raises(Exception, match="append-only"):
                await s.execute(text(statement), {"u": a.id})
            await s.rollback()


def test_transfer_time_parsing() -> None:
    now = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)  # 14:00 in Tashkent
    assert parse_transfer_time("13:35", now) == datetime(2026, 11, 20, 8, 35, tzinfo=UTC)
    assert parse_transfer_time("23:10", now) == datetime(2026, 11, 19, 18, 10, tzinfo=UTC)
    assert parse_transfer_time("19.11 22:05", now) == datetime(2026, 11, 19, 17, 5, tzinfo=UTC)
    assert parse_transfer_time("19.11.2026 22:05", now) == datetime(2026, 11, 19, 17, 5, tzinfo=UTC)
    assert parse_transfer_time("kecha", now) is None
    assert parse_transfer_time("31.02 10:00", now) is None


def test_migrations_0010_and_0011_downgrade_and_upgrade() -> None:
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": _URL}
    alembic = [sys.executable, "-m", "alembic"]

    def run(*args: str) -> str:
        done = subprocess.run(
            [*alembic, *args], cwd=root, env=env, capture_output=True, text=True, timeout=120
        )
        assert done.returncode == 0, done.stderr[-2000:]
        return done.stdout + done.stderr

    run("downgrade", "0009_admin_edit")
    assert "0009_admin_edit" in run("current")
    run("upgrade", "0010_payment_trust")
    assert "0010_payment_trust" in run("current")
    run("upgrade", "head")
    cfg = Config(str(root / "alembic.ini"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    assert f"{head} (head)" in run("current")
