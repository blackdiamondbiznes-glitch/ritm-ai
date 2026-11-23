"""Claim a delivery row and, when it should leave, add one job."""

from __future__ import annotations

from datetime import datetime

from app.db.models.jobs import Job, JobStatus
from app.db.repositories.jobs import JobRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.services.notify_rules import NOTIFY


async def deliver(
    notes: TutorNoticeRepository,
    jobs: JobRepository,
    *,
    kind: str,
    ref: int,
    target: str,
    target_id: int,
    telegram_id: int | None,
    lang: str,
    template: str,
    params: dict[str, object],
    quota: bool,
    owner_id: int,
    run_at: datetime,
    skip: bool = False,
) -> bool:
    """Return True when a new job was queued. A second call for the same event adds nothing."""
    skipped = skip or telegram_id is None
    notice_id = await notes.claim(kind, ref, target, target_id, "skipped" if skipped else "failed")
    if notice_id is None or skipped:
        return False
    await jobs.add(
        Job(
            chat_id=None,
            type=NOTIFY,
            payload={
                "notification_id": notice_id,
                "telegram_id": telegram_id,
                "lang": lang,
                "template": template,
                "params": params,
                "quota": quota,
                "owner_id": owner_id,
                "kind": kind,
            },
            run_at=run_at,
            status=JobStatus.PENDING,
            attempts=0,
            max_attempts=5,
        )
    )
    return True
