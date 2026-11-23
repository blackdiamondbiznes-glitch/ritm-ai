"""Sign a group member up when they tap the registration button."""

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import EnrollCB
from app.bot.enroll_notice import teacher_notifier
from app.bot.keyboards.menu import main_menu
from app.db.models.users import User
from app.i18n import t
from app.services.enrollment import EnrollmentService
from app.services.roles import RoleService

logger = logging.getLogger(__name__)

router = Router(name="enroll")


@router.callback_query(EnrollCB.filter())
async def on_group_enroll(
    callback: CallbackQuery,
    callback_data: EnrollCB,
    session: AsyncSession,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    bot: Bot,
    modes: RoleService | None = None,
) -> None:
    """Save the request, then answer in the group and in the private chat."""
    result = await enrollment.enroll(
        callback_data.c,
        current_user.telegram_id,
        current_user.full_name or "",
        notify=teacher_notifier(bot),
    )
    await session.commit()
    text = t(f"enroll_{result}", lang)[:200]
    logger.info("group enroll result=%s user_id=%s", result, current_user.telegram_id)
    teaching = False
    learning = False
    if modes is not None:
        found = await modes.for_user(current_user)
        teaching = bool(found["teaching"])
        learning = bool(found["learning"])
    await callback.answer(text, show_alert=True)
    try:
        await bot.send_message(
            current_user.telegram_id,
            text,
            reply_markup=main_menu(lang, is_super_admin, teaching=teaching, learning=learning),
        )
    except TelegramAPIError:
        logger.info("group enroll dm skipped user_id=%s", current_user.telegram_id)
