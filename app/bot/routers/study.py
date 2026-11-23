"""O'qishim sends a short summary and a button into the student Mini App."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import MenuCB
from app.bot.keyboards.menu import _menu_webapp_url, study_keyboard
from app.bot.widgets.send import send_card
from app.db.models.users import User
from app.services.learning import LearningService
from app.services.study_text import summary
from app.services.widget_cards import lesson_data

router = Router(name="study")


@router.callback_query(MenuCB.filter(F.a == "learn"))
async def learn_screen(
    callback: CallbackQuery,
    lang: str,
    current_user: User,
    learning: LearningService | None = None,
) -> None:
    """Reply with the next lesson and homework card, plus a Mini App button."""
    if learning is None or callback.message is None:
        await callback.answer()
        return
    payload = await learning.for_user(current_user)
    caption = summary(payload, lang)
    markup = study_keyboard(lang, _menu_webapp_url())
    data = _card(payload, lang)
    enabled = True
    try:
        from app.config import get_settings

        enabled = get_settings().widgets_enabled
    except Exception:
        enabled = True
    if data is not None:
        await send_card(
            callback.bot,
            chat_id=callback.message.chat.id,
            kind="lesson",
            data=data,
            caption=caption,
            markup=markup,
            allow_queries=False,
            enabled=enabled,
        )
    else:
        await callback.message.answer(caption, reply_markup=markup)
    await callback.answer()


def _card(payload: dict, lang: str) -> dict | None:
    groups = payload.get("groups") or []
    if not groups:
        return None
    item = groups[0]
    group = item.get("group") or {}
    session = item.get("next_session") or {}
    work = (item.get("homework") or [None])[0] or {}
    return lesson_data(
        lang,
        group.get("name") or "",
        group.get("teacher_name") or "",
        session.get("starts_at"),
        work.get("text") or "",
        work.get("due_on"),
    )
