"""Monthly bills, package lessons, and payment rules."""

import os
from datetime import UTC, date, datetime

import pytest
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.users import UserRepository
from app.services.attendance import AttendanceService
from app.services.fee_pay import FeePay
from app.services.fee_rules import invoice_status, periods_due
from app.services.fee_usage import PackageUsage
from app.services.fees import FeeError, FeeService
from app.services.tutor_limits import TutorLimitError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER = 9864300001


def test_periods_wait_for_the_billing_day_and_status_follows_the_date() -> None:
    start = date(2026, 11, 1)
    assert periods_due(16, start, date(2026, 11, 10)) == []
    assert periods_due(16, start, date(2026, 11, 16)) == [(date(2026, 11, 16), date(2026, 12, 15))]
    assert len(periods_due(16, start, date(2026, 12, 16))) == 2
    due = date(2026, 11, 21)
    assert invoice_status(0, 100, due, date(2026, 11, 21), "due") == "due"
    assert invoice_status(0, 100, due, date(2026, 11, 22), "due") == "overdue"
    assert invoice_status(100, 100, due, date(2026, 11, 22), "overdue") == "paid"
    assert invoice_status(0, 100, due, date(2026, 12, 1), "waived") == "waived"


class _Clock:
    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self):
        return datetime(self.day.year, self.day.month, self.day.day, 3, 0, tzinfo=UTC)


class _Access:
    def __init__(self, fees: bool, code: str = "free") -> None:
        self._fees = fees
        self._code = code

    async def tutor_limits(self, _owner):
        return type("Limits", (), {"fees": self._fees, "plan_code": self._code})()


async def _wipe(session) -> None:
    from app.db.models.invoices import TutorFeePayment, TutorInvoice

    ids = select(User.id).where(User.telegram_id == OWNER)
    invoices = select(TutorInvoice.id).where(
        TutorInvoice.group_id.in_(select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids)))
    )
    await session.execute(delete(TutorFeePayment).where(TutorFeePayment.invoice_id.in_(invoices)))
    await session.execute(
        delete(TutorInvoice).where(
            TutorInvoice.group_id.in_(select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids)))
        )
    )
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
    await session.execute(
        delete(TutorGroupMember).where(
            TutorGroupMember.group_id.in_(select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids)))
        )
    )
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id == OWNER))


@pytest.fixture
async def db():
    if not _URL.startswith("postgresql"):
        pytest.skip("Postgres is required")
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _wipe(session)
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await _wipe(session)
            await session.commit()
        await engine.dispose()


async def _world(session, mode: str, lessons: int | None, day: int | None) -> dict:
    user = User(telegram_id=OWNER, full_name="Lola", language_code="uz")
    session.add(user)
    await session.flush()
    space = Workspace(owner_id=user.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    group = TutorGroup(
        owner_id=user.id,
        workspace_id=space.id,
        name="Ingliz",
        weekdays="1",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code="feephase4",
        fee_mode=mode,
        fee_uzs=100_000,
        package_lessons=lessons,
        billing_day=day,
        due_days=5,
    )
    session.add(group)
    await session.flush()
    student = TutorStudent(
        owner_id=user.id,
        workspace_id=space.id,
        name="Ali",
        status="paid",
        amount_uzs=0,
        join_code="feeali01",
    )
    session.add(student)
    await session.flush()
    link = TutorGroupMember(
        group_id=group.id,
        student_id=student.id,
        status="active",
        billing_start=date(2026, 11, 1),
    )
    session.add(link)
    await session.flush()
    return {"user": user, "group": group, "student": student, "link": link}


def _fees(session, clock: _Clock, access: _Access | None = None) -> FeeService:
    return FeeService(
        InvoiceRepository(session),
        GroupRepository(session),
        UserRepository(session),
        access,
        clock,
    )


async def test_monthly_is_idempotent_and_payments_restore_status(db) -> None:
    async with db() as session:
        clock = _Clock(date(2026, 11, 10))
        ids = await _world(session, "monthly", None, 16)
        fees = _fees(session, clock)
        assert await fees.sync_group(ids["group"]) == 1
        assert await fees.sync_group(ids["group"]) == 0
        clock.day = date(2026, 11, 16)
        assert await fees.sync_group(ids["group"]) == 0
        rows = await InvoiceRepository(session).for_member(ids["group"].id, ids["student"].id)
        assert rows[0].amount_uzs == 100_000 and rows[0].due_on == date(2026, 11, 21)
        assert rows[0].status == "due"
        clock.day = date(2026, 11, 22)
        await fees.run_daily()
        await session.refresh(rows[0])
        assert rows[0].status == "overdue"
        pay = FeePay(InvoiceRepository(session), fees, _Access(True, "start"), clock)
        partial = await pay.pay(
            ids["user"].id,
            rows[0].id,
            {"amount_uzs": 40_000, "paid_on": "2026-11-22", "method": "cash"},
        )
        assert partial["status"] == "overdue" and partial["paid_uzs"] == 40_000
        full = await pay.pay(
            ids["user"].id,
            rows[0].id,
            {"amount_uzs": 60_000, "paid_on": "2026-11-22", "method": "card"},
        )
        assert full["status"] == "paid"
        with pytest.raises(FeeError) as over:
            await pay.pay(
                ids["user"].id,
                rows[0].id,
                {"amount_uzs": 1, "paid_on": "2026-11-22", "method": "cash"},
            )
        assert over.value.code == "amount"
        found = list(
            (
                await session.execute(
                    select(TutorFeePayment).where(TutorFeePayment.invoice_id == rows[0].id)
                )
            ).scalars()
        )
        big = next(item for item in found if item.amount_uzs == 60_000)
        restored = await pay.remove(ids["user"].id, big.id)
        assert restored["paid_uzs"] == 40_000 and restored["status"] == "overdue"
        blocked = FeePay(InvoiceRepository(session), fees, _Access(False), clock)
        with pytest.raises(TutorLimitError) as free:
            await blocked.pay(
                ids["user"].id,
                rows[0].id,
                {"amount_uzs": 1, "paid_on": "2026-11-22", "method": "cash"},
            )
        assert free.value.code == "limit_fees"
        waived = await pay.waive(ids["user"].id, rows[0].id)
        assert waived["status"] == "waived"
        with pytest.raises(FeeError) as closed:
            await pay.pay(
                ids["user"].id,
                rows[0].id,
                {"amount_uzs": 1, "paid_on": "2026-11-22", "method": "cash"},
            )
        assert closed.value.code == "status"
        ids["link"].fee_override_uzs = 50_000
        ids["group"].fee_uzs = 200_000
        await session.flush()
        clock.day = date(2026, 12, 16)
        await fees.sync_group(ids["group"])
        again = await InvoiceRepository(session).for_member(ids["group"].id, ids["student"].id)
        assert [row.amount_uzs for row in again] == [100_000, 50_000]


async def test_the_twelfth_lesson_opens_the_next_package(db) -> None:
    async with db() as session:
        clock = _Clock(date(2026, 11, 16))
        ids = await _world(session, "package", 12, None)
        fees = _fees(session, clock)
        usage = PackageUsage(InvoiceRepository(session), GroupRepository(session), fees, clock)
        assert await fees.sync_group(ids["group"]) == 1
        for _ in range(12):
            await usage.adjust(ids["group"].id, [(ids["student"].id, 1)])
        rows = await InvoiceRepository(session).for_member(ids["group"].id, ids["student"].id)
        packages = [row for row in rows if row.kind == "package"]
        assert len(packages) == 2
        assert packages[0].lessons_used == 12 and packages[1].lessons_used == 0
        await usage.adjust(ids["group"].id, [(ids["student"].id, -1)])
        await session.refresh(packages[0])
        assert packages[0].lessons_used == 11
        lesson = TutorLesson(
            owner_id=ids["user"].id,
            workspace_id=ids["group"].workspace_id,
            group_id=ids["group"].id,
            title="Dars",
            status="scheduled",
            amount_uzs=0,
            starts_at=datetime(2026, 11, 16, 13, 0, tzinfo=UTC),
            ends_at=datetime(2026, 11, 16, 14, 0, tzinfo=UTC),
            planned_at=datetime(2026, 11, 16, 13, 0, tzinfo=UTC),
        )
        session.add(lesson)
        await session.flush()
        attendance = AttendanceService(
            AttendanceRepository(session),
            LessonRepository(session),
            GroupRepository(session),
            now=clock,
            fees=usage,
        )
        await attendance.save(
            ids["user"].id,
            lesson.id,
            {"marks": [{"student_id": ids["student"].id, "status": "present"}]},
        )
        await session.refresh(packages[0])
        assert packages[0].lessons_used == 12
        await attendance.save(
            ids["user"].id, lesson.id, {"marks": [{"student_id": ids["student"].id, "status": ""}]}
        )
        await session.refresh(packages[0])
        assert packages[0].lessons_used == 11
