"""Screen texts. Dynamic values are escaped before HTML parse mode."""

from html import escape

from app.db.models.chats import Chat, ChatProfile
from app.i18n import t
from app.services.access import PlanSnapshot
from app.services.leaderboard import BoardView, MemberScore
from app.services.scoring import medal


def niche_label(code: str, lang: str) -> str:
    """Preset label, or the custom text escaped."""
    key = f"niche_{code}"
    label = t(key, lang)
    if label == key:
        return escape(code)
    return label


def chat_card_text(
    chat: Chat,
    snap: PlanSnapshot,
    profile: ChatProfile | None,
    lang: str,
    *,
    note: str | None = None,
) -> str:
    """Short card: title, type, plan, days, profile."""
    plan = _plan_name(snap, lang)
    days = t("days_none", lang) if snap.days_left is None else str(snap.days_left)
    body = t(
        "chat_card",
        lang,
        title=escape(chat.title),
        kind=t(f"type_{chat.type.value}", lang),
        plan=plan,
        days=days,
        profile=_profile_line(profile, lang),
    )
    if note:
        return f"{note}\n\n{body}"
    return body


def summary_text(data: dict[str, object], lang: str) -> str:
    """Wizard review. User text is escaped."""
    niche = str(data.get("niche_code", ""))
    desc = str(data.get("niche_description", ""))
    if len(desc) > 120:
        desc = desc[:117] + "..."
    return t(
        "wizard_summary",
        lang,
        niche=niche_label(niche, lang),
        desc=escape(desc),
        tone=t(f"tone_{data.get('tone')}", lang),
        level=t(f"aud_{data.get('audience_level')}", lang),
        content_lang=t(f"lang_{data.get('language')}", lang),
        tz=escape(str(data.get("timezone", ""))),
    )


def _plan_name(snap: PlanSnapshot, lang: str) -> str:
    name = escape(snap.plan.name)
    if snap.kind == "trial":
        return t("plan_trial", lang, name=name)
    if snap.kind == "active":
        return t("plan_active", lang, name=name)
    return t("plan_free", lang, name=name)


def _profile_line(profile: ChatProfile | None, lang: str) -> str:
    if profile is None:
        return t("no_profile", lang)
    return " · ".join(
        (
            niche_label(profile.niche_code, lang),
            t(f"tone_{profile.tone}", lang),
            t(f"aud_{profile.audience_level}", lang),
        )
    )


def quiz_question_html(question: str) -> str:
    """Escape a quiz question for the bot's default HTML parse mode."""
    return escape(question)


def board_announcement(view: BoardView, lang: str) -> str:
    """Weekly Top-10 posted into the connected chat. Names are escaped."""
    body = _board_lines(view, lang)
    return t(
        "board_post",
        lang,
        range=_date_range(view, lang),
        lines=body,
    )


def board_screen(
    last: BoardView | None,
    live: BoardView,
    lang: str,
    *,
    weekday: str,
    clock: str,
    state: str,
    note: str | None = None,
) -> str:
    """Private Reyting screen: last announced week plus a live preview."""
    last_block = t("board_last_empty", lang)
    if last is not None:
        last_block = t(
            "board_last",
            lang,
            range=_date_range(last, lang),
            lines=_board_lines(last, lang),
        )
    live_lines = _board_lines(live, lang) if live.members else t("board_live_empty", lang)
    text = t(
        "board_screen",
        lang,
        last=last_block,
        live_range=_date_range(live, lang),
        live_lines=live_lines,
        weekday=weekday,
        time=clock,
        state=state,
    )
    if note:
        return f"{note}\n\n{text}"
    return text


def _board_lines(view: BoardView, lang: str) -> str:
    lines = [_board_line(item, lang) for item in view.members[:10]]
    return "\n".join(lines)


def _board_line(item: MemberScore, lang: str) -> str:
    return t(
        "board_line",
        lang,
        rank=item.rank,
        medal=medal(item.rank),
        name=_mention(item),
        points=item.score.points,
        correct=item.score.correct_count,
        total=item.score.total_answers,
    )


def _mention(item: MemberScore) -> str:
    label = escape(_display_name(item.full_name, item.username))
    if item.telegram_id:
        return f'<a href="tg://user?id={int(item.telegram_id)}">{label}</a>'
    return label


def _display_name(full_name: str | None, username: str | None) -> str:
    name = (full_name or "").strip()
    if name:
        return name
    handle = (username or "").strip()
    if handle:
        return f"@{handle}"
    return "—"


def _date_range(view: BoardView, lang: str) -> str:
    return t(
        "board_range",
        lang,
        start=view.start.strftime("%d.%m.%Y"),
        end=view.end.strftime("%d.%m.%Y"),
    )
