"""Magic links for the teacher web panel: random, hashed at rest, 15 minutes, single use."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.panel_tokens import PanelLoginToken
from app.db.models.users import User
from app.db.repositories.workspaces import WorkspaceRepository
from app.i18n import t
from app.services.clock import utcnow

logger = logging.getLogger(__name__)
TTL = timedelta(minutes=15)
TOKEN_BYTES = 32
TOKEN_MAX = 128


def token_hash(raw: str) -> str:
    """SHA-256 hex of the raw token. The raw value never reaches the database or logs."""
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue(session: AsyncSession, user_id: int, now: datetime | None = None) -> str:
    """Store a new link for this user and return the raw token. Old spent links are pruned."""
    stamp = now or utcnow()
    await session.execute(
        delete(PanelLoginToken).where(
            PanelLoginToken.user_id == user_id,
            or_(PanelLoginToken.used_at.is_not(None), PanelLoginToken.expires_at < stamp),
        )
    )
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(
        PanelLoginToken(user_id=user_id, token_hash=token_hash(raw), expires_at=stamp + TTL)
    )
    await session.flush()
    return raw


async def consume(session: AsyncSession, raw: str, now: datetime | None = None) -> int | None:
    """Mark the link used in one statement and return its user id, or None if spent or stale."""
    if not raw or len(raw) > TOKEN_MAX:
        return None
    stamp = now or utcnow()
    stmt = (
        update(PanelLoginToken)
        .where(
            PanelLoginToken.token_hash == token_hash(raw),
            PanelLoginToken.used_at.is_(None),
            PanelLoginToken.expires_at > stamp,
        )
        .values(used_at=stamp)
        .returning(PanelLoginToken.user_id)
    )
    row = (await session.execute(stmt)).first()
    return int(row[0]) if row else None


async def is_teacher(session: AsyncSession, user: User) -> bool:
    """A cabinet with at least one group or student."""
    rows = await WorkspaceRepository(session).teaching_for(user.id)
    return any(groups > 0 or students > 0 for _space, groups, students in rows)


def login_url(base: str, raw: str) -> str:
    return f"{base.rstrip('/')}/panel/login?t={raw}"


async def send_link(bot: Bot, session: AsyncSession, user: User, base: str, lang: str) -> bool:
    """Issue a link and send it as a URL button (buttons get no link preview)."""
    raw = await issue(session, user.id)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("panel_link_btn", lang), url=login_url(base, raw))]
        ]
    )
    try:
        await bot.send_message(
            user.telegram_id,
            t("panel_link_text", lang),
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramAPIError:
        logger.info("panel link not delivered user=%s", user.id)
        return False
    return True
