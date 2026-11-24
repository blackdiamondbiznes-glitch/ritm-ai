"""Har bir tutor API yo‘li boshqa egasining ma’lumoti bilan tekshiriladi."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.services.clock import TASHKENT
from sqlalchemy import select
from tests.test_export_http import OTHER, PRO, client  # noqa: F401

_TUTOR_ROUTES = {
    ("GET", "/api/tutor/groups"),
    ("POST", "/api/tutor/groups"),
    ("GET", "/api/tutor/groups/{group_id}"),
    ("PATCH", "/api/tutor/groups/{group_id}"),
    ("DELETE", "/api/tutor/groups/{group_id}"),
    ("POST", "/api/tutor/groups/{group_id}/students"),
    ("POST", "/api/tutor/groups/{group_id}/announce"),
    ("DELETE", "/api/tutor/groups/{group_id}/students/{student_id}"),
    ("GET", "/api/tutor/sessions/{session_id}/attendance"),
    ("PUT", "/api/tutor/sessions/{session_id}/attendance"),
    ("GET", "/api/tutor/groups/{group_id}/attendance"),
    ("GET", "/api/tutor/requests"),
    ("POST", "/api/tutor/requests/{group_id}/{student_id}/approve"),
    ("POST", "/api/tutor/requests/{group_id}/{student_id}/reject"),
    ("GET", "/api/tutor/groups/{group_id}/board"),
    ("POST", "/api/tutor/groups/{group_id}/topics"),
    ("GET", "/api/tutor/groups/{group_id}/topics/{topic_id}"),
    ("PUT", "/api/tutor/groups/{group_id}/topics/{topic_id}"),
    ("PUT", "/api/tutor/groups/{group_id}/topics/{topic_id}/homework"),
    ("GET", "/api/tutor/summary"),
    ("POST", "/api/tutor/enable"),
    ("POST", "/api/tutor/name"),
    ("GET", "/api/tutor/lessons"),
    ("POST", "/api/tutor/lessons"),
    ("PATCH", "/api/tutor/lessons/{lesson_id}"),
    ("DELETE", "/api/tutor/lessons/{lesson_id}"),
    ("GET", "/api/tutor/students"),
    ("GET", "/api/tutor/students/{student_id}"),
    ("POST", "/api/tutor/students"),
    ("PATCH", "/api/tutor/students/{student_id}"),
    ("DELETE", "/api/tutor/students/{student_id}"),
    ("PUT", "/api/tutor/groups/{group_id}/fee"),
    ("PUT", "/api/tutor/groups/{group_id}/members/{student_id}/fee"),
    ("GET", "/api/tutor/invoices"),
    ("POST", "/api/tutor/invoices/{invoice_id}/payments"),
    ("DELETE", "/api/tutor/payments/{payment_id}"),
    ("POST", "/api/tutor/invoices/{invoice_id}/waive"),
    ("GET", "/api/tutor/fees/summary"),
    ("GET", "/api/tutor/export/students.csv"),
    ("GET", "/api/tutor/export/payments.csv"),
    ("GET", "/api/tutor/export/attendance.csv"),
    ("GET", "/api/tutor/reports/monthly"),
    ("GET", "/api/tutor/limits"),
    ("GET", "/api/tutor/sessions"),
    ("POST", "/api/tutor/groups/{group_id}/sessions"),
    ("PATCH", "/api/tutor/sessions/{session_id}"),
    ("GET", "/api/tutor/reminders"),
    ("POST", "/api/tutor/reminders"),
    ("DELETE", "/api/tutor/reminders/{reminder_id}"),
    ("GET", "/api/tutor/groups/{group_id}/notify"),
    ("PUT", "/api/tutor/groups/{group_id}/notify"),
    ("PUT", "/api/tutor/groups/{group_id}/chat"),
}


async def test_every_tutor_route_is_scoped_to_the_signed_in_owner(
    client,  # noqa: F811
) -> None:
    http, heads, sessions = client
    today = datetime.now(TASHKENT).date()
    session_day = today + timedelta(days=3)
    reminder_day = today + timedelta(days=4)
    month = today.strftime("%Y-%m")
    owner_auth = heads["pro"]
    other_auth = heads["other"]
    exercised: set[tuple[str, str]] = set()

    async def call(
        method: str,
        route: str,
        path: str,
        *,
        status: int = 404,
        body: dict | None = None,
    ):
        route_method, _, route_path = route.partition(" ")
        assert route_method == method
        exercised.add((method, route_path))
        kwargs = {"headers": owner_auth}
        if body is not None:
            kwargs["json"] = body
        response = await http.request(method, path, **kwargs)
        assert response.status == status, f"{method} {path}: {await response.text()}"
        return response

    foreign_group = await http.post(
        "/api/tutor/groups",
        headers=other_auth,
        json={"name": "Begona guruh", "weekdays": [1], "start": "18:00", "end": "19:00"},
    )
    assert foreign_group.status == 200
    foreign_group_id = (await foreign_group.json())["created_id"]
    foreign_student = await http.post(
        "/api/tutor/students",
        headers=other_auth,
        json={
            "name": "Begona o‘quvchi",
            "status": "paid",
            "group_ids": [foreign_group_id],
        },
    )
    assert foreign_student.status == 200
    foreign_student_id = (await foreign_student.json())["created_id"]

    async with sessions() as session:
        owner = (
            await session.execute(select(User).where(User.telegram_id == PRO))
        ).scalar_one()
        other = (
            await session.execute(select(User).where(User.telegram_id == OTHER))
        ).scalar_one()
        group = await session.get(TutorGroup, foreign_group_id)
        assert group is not None
        member = (
            await session.execute(
                select(TutorGroupMember).where(
                    TutorGroupMember.group_id == foreign_group_id,
                    TutorGroupMember.student_id == foreign_student_id,
                )
            )
        ).scalar_one()
        member.billing_start = today.replace(day=1)
        pending = TutorStudent(
            owner_id=other.id,
            workspace_id=group.workspace_id,
            name="Kutilayotgan o‘quvchi",
            status="pending",
            amount_uzs=0,
            join_code="mtxpend01",
        )
        session.add(pending)
        await session.flush()
        session.add(
            TutorGroupMember(
                group_id=foreign_group_id,
                student_id=pending.id,
                status="pending",
            )
        )
        owner_id, other_id = owner.id, other.id
        await session.commit()

    priced = await http.put(
        f"/api/tutor/groups/{foreign_group_id}/fee",
        headers=other_auth,
        json={
            "fee_mode": "monthly",
            "fee_uzs": 300_000,
            "billing_day": min(today.day, 28),
            "due_days": 10,
        },
    )
    assert priced.status == 200
    async with sessions() as session:
        invoice = (
            await session.execute(
                select(TutorInvoice).where(TutorInvoice.group_id == foreign_group_id)
            )
        ).scalar_one()
        invoice.paid_uzs = invoice.amount_uzs
        invoice.status = "paid"
        payment = TutorFeePayment(
            invoice_id=invoice.id,
            amount_uzs=invoice.amount_uzs,
            paid_on=today,
            method="cash",
            created_by=other_id,
        )
        session.add(payment)
        await session.flush()
        foreign_invoice_id, foreign_payment_id = invoice.id, payment.id
        await session.commit()

    foreign_session = await http.post(
        f"/api/tutor/groups/{foreign_group_id}/sessions",
        headers=other_auth,
        json={
            "title": "Begona mashg‘ulot",
            "starts_at": f"{session_day.isoformat()}T10:00",
            "ends_at": f"{session_day.isoformat()}T11:00",
        },
    )
    assert foreign_session.status == 200
    sessions_response = await http.get(
        f"/api/tutor/sessions?from={session_day}&to={session_day}", headers=other_auth
    )
    foreign_session_rows = await sessions_response.json()
    foreign_session_id = next(
        row["id"]
        for row in foreign_session_rows
        if row["group_id"] == foreign_group_id and row["title"] == "Begona mashg‘ulot"
    )

    foreign_lesson = await http.post(
        "/api/tutor/lessons",
        headers=other_auth,
        json={
            "title": "Begona yakka dars",
            "student_id": foreign_student_id,
            "starts_at": f"{session_day.isoformat()}T13:00",
            "status": "scheduled",
        },
    )
    assert foreign_lesson.status == 200
    foreign_lesson_id = next(
        item["id"]
        for item in (await foreign_lesson.json())["lessons"]
        if item["title"] == "Begona yakka dars"
    )
    topic_response = await http.post(
        f"/api/tutor/groups/{foreign_group_id}/topics",
        headers=other_auth,
        json={"title": "Begona mavzu", "held_on": today.isoformat()},
    )
    assert topic_response.status == 200
    foreign_topic_id = (await topic_response.json())["topic"]["id"]
    reminder_response = await http.post(
        "/api/tutor/reminders",
        headers=other_auth,
        json={
            "text": "Begona eslatma",
            "send_at": f"{reminder_day.isoformat()}T09:00",
            "audience": "group",
            "group_id": foreign_group_id,
        },
    )
    assert reminder_response.status == 200
    foreign_reminder_id = (await reminder_response.json())["reminders"][0]["id"]

    app_routes = {
        (route.method, route.resource.canonical)
        for route in http.app.router.routes()
        if route.resource.canonical.startswith("/api/tutor/")
        and route.method not in {"HEAD", "OPTIONS"}
    }
    assert app_routes == _TUTOR_ROUTES

    groups = await call("GET", "GET /api/tutor/groups", "/api/tutor/groups", status=200)
    assert (await groups.json())["groups"] == []
    students = await call("GET", "GET /api/tutor/students", "/api/tutor/students", status=200)
    assert (await students.json())["students"] == []
    requests = await call("GET", "GET /api/tutor/requests", "/api/tutor/requests", status=200)
    assert (await requests.json())["requests"] == []
    lessons = await call("GET", "GET /api/tutor/lessons", "/api/tutor/lessons", status=200)
    assert (await lessons.json())["lessons"] == []
    reminders = await call(
        "GET", "GET /api/tutor/reminders", "/api/tutor/reminders", status=200
    )
    assert (await reminders.json())["reminders"] == []

    await call(
        "GET",
        "GET /api/tutor/groups/{group_id}",
        f"/api/tutor/groups/{foreign_group_id}",
    )
    await call(
        "PATCH",
        "PATCH /api/tutor/groups/{group_id}",
        f"/api/tutor/groups/{foreign_group_id}",
        body={"name": "O‘zgartirish"},
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/groups/{group_id}",
        f"/api/tutor/groups/{foreign_group_id}",
    )
    await call(
        "POST",
        "POST /api/tutor/groups/{group_id}/students",
        f"/api/tutor/groups/{foreign_group_id}/students",
        body={"student_id": foreign_student_id},
    )
    await call(
        "POST",
        "POST /api/tutor/groups/{group_id}/announce",
        f"/api/tutor/groups/{foreign_group_id}/announce",
        body={"text": "Salom", "to_chat": True, "to_students": True},
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/groups/{group_id}/students/{student_id}",
        f"/api/tutor/groups/{foreign_group_id}/students/{foreign_student_id}",
    )
    await call(
        "GET",
        "GET /api/tutor/groups/{group_id}/notify",
        f"/api/tutor/groups/{foreign_group_id}/notify",
    )
    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/notify",
        f"/api/tutor/groups/{foreign_group_id}/notify",
        body={"remind_lesson_min": 15, "remind_fee_days": None, "fee_in_group": False},
    )
    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/chat",
        f"/api/tutor/groups/{foreign_group_id}/chat",
        body={"chat_id": None},
    )
    await call(
        "GET",
        "GET /api/tutor/groups/{group_id}/attendance",
        f"/api/tutor/groups/{foreign_group_id}/attendance?month={month}",
    )
    await call(
        "POST",
        "POST /api/tutor/requests/{group_id}/{student_id}/approve",
        f"/api/tutor/requests/{foreign_group_id}/{foreign_student_id}/approve",
        status=404,
        body={},
    )
    await call(
        "POST",
        "POST /api/tutor/requests/{group_id}/{student_id}/reject",
        f"/api/tutor/requests/{foreign_group_id}/{foreign_student_id}/reject",
        status=404,
        body={},
    )
    await call(
        "GET",
        "GET /api/tutor/groups/{group_id}/board",
        f"/api/tutor/groups/{foreign_group_id}/board",
    )
    await call(
        "POST",
        "POST /api/tutor/groups/{group_id}/topics",
        f"/api/tutor/groups/{foreign_group_id}/topics",
        body={"title": "O‘g‘irlangan mavzu", "held_on": today.isoformat()},
    )
    await call(
        "GET",
        "GET /api/tutor/groups/{group_id}/topics/{topic_id}",
        f"/api/tutor/groups/{foreign_group_id}/topics/{foreign_topic_id}",
    )
    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/topics/{topic_id}",
        f"/api/tutor/groups/{foreign_group_id}/topics/{foreign_topic_id}",
        body={},
    )
    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/topics/{topic_id}/homework",
        f"/api/tutor/groups/{foreign_group_id}/topics/{foreign_topic_id}/homework",
        body={"homework": "Begona vazifa", "homework_due": today.isoformat()},
    )

    summary = await call("GET", "GET /api/tutor/summary", "/api/tutor/summary", status=200)
    summary_body = await summary.json()
    assert summary_body["students"]["debtor"] == 0
    assert summary_body["lessons"]["scheduled"] == 0
    enabled = await call("POST", "POST /api/tutor/enable", "/api/tutor/enable", status=200, body={})
    assert (await enabled.json())["students"]["debtor"] == 0
    named = await call(
        "POST", "POST /api/tutor/name", "/api/tutor/name", status=200, body={"name": "O‘qituvchi"}
    )
    assert (await named.json())["teacher_name"] == "O‘qituvchi"
    other_summary = await http.get("/api/tutor/summary", headers=other_auth)
    assert (await other_summary.json())["teacher_name"] == ""

    await call(
        "POST",
        "POST /api/tutor/lessons",
        "/api/tutor/lessons",
        status=404,
        body={
            "title": "Begona o‘quvchiga dars",
            "student_id": foreign_student_id,
            "starts_at": f"{session_day.isoformat()}T14:00",
        },
    )
    await call(
        "PATCH",
        "PATCH /api/tutor/lessons/{lesson_id}",
        f"/api/tutor/lessons/{foreign_lesson_id}",
        body={"status": "done"},
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/lessons/{lesson_id}",
        f"/api/tutor/lessons/{foreign_lesson_id}",
    )
    await call(
        "GET",
        "GET /api/tutor/students/{student_id}",
        f"/api/tutor/students/{foreign_student_id}",
    )
    own_student = await call(
        "POST",
        "POST /api/tutor/students",
        "/api/tutor/students",
        status=200,
        body={"name": "O‘z o‘quvchim", "owner_id": other_id},
    )
    own_student_id = (await own_student.json())["created_id"]
    await call(
        "POST",
        "POST /api/tutor/students",
        "/api/tutor/students",
        status=404,
        body={
            "name": "Begona guruhga qo‘shish",
            "group_ids": [foreign_group_id],
        },
    )
    await call(
        "PATCH",
        "PATCH /api/tutor/students/{student_id}",
        f"/api/tutor/students/{foreign_student_id}",
        body={"name": "O‘zgartirish"},
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/students/{student_id}",
        f"/api/tutor/students/{foreign_student_id}",
    )

    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/fee",
        f"/api/tutor/groups/{foreign_group_id}/fee",
        body={"fee_mode": "none", "fee_uzs": 0, "due_days": 5},
    )
    await call(
        "PUT",
        "PUT /api/tutor/groups/{group_id}/members/{student_id}/fee",
        f"/api/tutor/groups/{foreign_group_id}/members/{foreign_student_id}/fee",
        body={"fee_override_uzs": 1000},
    )
    invoices = await call(
        "GET",
        "GET /api/tutor/invoices",
        f"/api/tutor/invoices?group_id={foreign_group_id}",
        status=200,
    )
    assert await invoices.json() == []
    await call(
        "POST",
        "POST /api/tutor/invoices/{invoice_id}/payments",
        f"/api/tutor/invoices/{foreign_invoice_id}/payments",
        body={"amount_uzs": 1, "paid_on": today.isoformat(), "method": "cash"},
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/payments/{payment_id}",
        f"/api/tutor/payments/{foreign_payment_id}",
    )
    await call(
        "POST",
        "POST /api/tutor/invoices/{invoice_id}/waive",
        f"/api/tutor/invoices/{foreign_invoice_id}/waive",
        body={},
    )
    fees = await call("GET", "GET /api/tutor/fees/summary", "/api/tutor/fees/summary", status=200)
    assert (await fees.json())["outstanding_uzs"] == 0

    student_export = await call(
        "GET",
        "GET /api/tutor/export/students.csv",
        "/api/tutor/export/students.csv",
        status=200,
    )
    assert "Begona o‘quvchi" not in await student_export.text()
    payment_export = await call(
        "GET",
        "GET /api/tutor/export/payments.csv",
        f"/api/tutor/export/payments.csv?month={month}",
        status=200,
    )
    assert "Begona guruh" not in await payment_export.text()
    await call(
        "GET",
        "GET /api/tutor/export/attendance.csv",
        f"/api/tutor/export/attendance.csv?group_id={foreign_group_id}&month={month}",
    )
    report = await call(
        "GET",
        "GET /api/tutor/reports/monthly",
        f"/api/tutor/reports/monthly?month={month}",
        status=200,
    )
    assert (await report.json())["groups"] == []
    limits = await call("GET", "GET /api/tutor/limits", "/api/tutor/limits", status=200)
    limits_body = await limits.json()
    assert limits_body["groups"]["used"] == 0
    assert limits_body["students"]["used"] == 1

    listed_sessions = await call(
        "GET",
        "GET /api/tutor/sessions",
        f"/api/tutor/sessions?from={session_day}&to={session_day}",
        status=200,
    )
    assert await listed_sessions.json() == []
    await call(
        "POST",
        "POST /api/tutor/groups/{group_id}/sessions",
        f"/api/tutor/groups/{foreign_group_id}/sessions",
        body={
            "title": "O‘g‘irlangan mashg‘ulot",
            "starts_at": f"{session_day.isoformat()}T15:00",
            "ends_at": f"{session_day.isoformat()}T16:00",
        },
    )
    await call(
        "PATCH",
        "PATCH /api/tutor/sessions/{session_id}",
        f"/api/tutor/sessions/{foreign_session_id}",
        body={"status": "cancelled"},
    )
    await call(
        "GET",
        "GET /api/tutor/sessions/{session_id}/attendance",
        f"/api/tutor/sessions/{foreign_session_id}/attendance",
    )
    await call(
        "PUT",
        "PUT /api/tutor/sessions/{session_id}/attendance",
        f"/api/tutor/sessions/{foreign_session_id}/attendance",
        body={},
    )

    await call(
        "POST",
        "POST /api/tutor/reminders",
        "/api/tutor/reminders",
        status=404,
        body={
            "text": "Begona guruhga eslatma",
            "send_at": f"{reminder_day.isoformat()}T10:00",
            "audience": "group",
            "group_id": foreign_group_id,
        },
    )
    await call(
        "DELETE",
        "DELETE /api/tutor/reminders/{reminder_id}",
        f"/api/tutor/reminders/{foreign_reminder_id}",
    )

    own_group = await call(
        "POST",
        "POST /api/tutor/groups",
        "/api/tutor/groups",
        status=200,
        body={
            "name": "O‘z guruhim",
            "weekdays": [1],
            "start": "18:00",
            "end": "19:00",
            "owner_id": other_id,
        },
    )
    own_group_id = (await own_group.json())["created_id"]
    await call(
        "POST",
        "POST /api/tutor/groups/{group_id}/students",
        f"/api/tutor/groups/{own_group_id}/students",
        body={"student_id": foreign_student_id},
    )
    async with sessions() as session:
        own_group_row = await session.get(TutorGroup, own_group_id)
        own_student_row = await session.get(TutorStudent, own_student_id)
        foreign_group_row = await session.get(TutorGroup, foreign_group_id)
        assert own_group_row is not None and own_group_row.owner_id == owner_id
        assert own_student_row is not None and own_student_row.owner_id == owner_id
        assert foreign_group_row is not None and foreign_group_row.owner_id == other_id

    assert exercised == _TUTOR_ROUTES
