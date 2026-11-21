"""Deliver one tutor reminder to the owner's private chat."""

import logging

from aiogram import Bot

from app.db.models.jobs import Job
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.users import UserRepository
from app.jobs.runner import JobCancel
from app.services.clock import utcnow
from app.services.reminders import REMINDER

logger = logging.getLogger(__name__)


class ReminderHandler:
    """Send the reminder text once, then mark it sent."""

    def __init__(
        self,
        bot: Bot,
        reminders: ReminderRepository,
        users: UserRepository,
        now=utcnow,
    ) -> None:
        self._bot = bot
        self._reminders = reminders
        self._users = users
        self._now = now

    async def handle(self, job: Job) -> None:
        """Send unless this reminder was already delivered or deleted."""
        raw = job.payload.get("reminder_id")
        if not isinstance(raw, int):
            raise JobCancel("reminder")
        row = await self._reminders.get(raw)
        if row is None or row.sent_at is not None:
            raise JobCancel("sent")
        user = await self._users.get_by_id(row.owner_id)
        if user is None:
            raise JobCancel("owner")
        await self._bot.send_message(user.telegram_id, row.text)
        row.sent_at = self._now()
        await self._reminders.save(row)
        logger.info("reminder sent id=%s owner_id=%s", row.id, row.owner_id)


__all__ = ["REMINDER", "ReminderHandler"]
