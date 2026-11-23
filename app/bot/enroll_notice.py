"""Messages sent when a student asks to join a group."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from app.bot.widgets.dispatch import remember
from app.bot.widgets.markup import cabinet_markup
from app.bot.widgets.send import send_card
from app.db.models.users import User
from app.i18n import t
from app.services.widget_cards import enroll_data, enroll_ref

logger = logging.getLogger(__name__)


async def tell(bot: Bot | None, chat_id: int | None, text: str) -> None:
    """Send a private notice. A blocked chat is ignored."""
    if bot is None or chat_id is None:
        return
    try:
        await bot.send_message(chat_id, text)
    except TelegramForbiddenError:
        logger.info("enroll notice skipped chat_id=%s", chat_id)


def ask_text(lang: str, name: str, group: str) -> str:
    """Teacher alert. Names are escaped because the bot parses HTML."""
    return t("enroll_ask", lang, name=escape(name), group=escape(group))


def decision_text(lang: str, key: str, group: str) -> str:
    """Student alert after the teacher decides."""
    return t(key, lang, group=escape(group))


def teacher_notifier(bot: Bot, session=None, *, enabled: bool | None = None):
    """Callback EnrollmentService calls after a new request is stored."""

    async def notify(
        owner: User, name: str, group_name: str, group_id: int = 0, student_id: int = 0
    ) -> None:
        lang = owner.language_code or "uz"
        text = ask_text(lang, name, group_name)
        if owner.telegram_id is None:
            return
        use = enabled
        if use is None:
            try:
                from app.config import get_settings

                use = get_settings().widgets_enabled
            except Exception:
                use = True
        if group_id and student_id:
            message = await send_card(
                bot,
                chat_id=owner.telegram_id,
                kind="enroll",
                data=enroll_data(lang, name, group_name, group_id, student_id),
                caption=text,
                markup=cabinet_markup(lang),
                allow_queries=True,
                enabled=use,
            )
            if session is not None:
                await remember(session, "enroll", enroll_ref(group_id, student_id), message)
            return
        await tell(bot, owner.telegram_id, text)

    return notify
