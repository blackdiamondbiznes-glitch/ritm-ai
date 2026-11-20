"""Owner Mini App actions. Every chat lookup re-checks ownership."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.bot.guard import manages
from app.db.models.chats import Chat
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.db.repositories.jobs import DAILY
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.leaderboard import MODULE as LEADERBOARD
from app.services.leaderboard import LeaderboardService
from app.services.profiles import (
    AUDIENCES,
    DESC_MAX,
    LANGUAGES,
    NICHE_MAX,
    PRESET_NICHES,
    TIMEZONES,
    TONES,
    ProfileError,
    ProfileInput,
    ProfileService,
)
from app.services.quiz_launch import QuizLaunch
from app.services.quiz_mode import ADMIN_POST_QUIZ, QUIZ
from app.services.schedule import ScheduleService, parse_clock


class PanelError(Exception):
    """HTTP-shaped failure: status and a stable error code."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


WEEKDAYS = frozenset(range(1, 8))

ROLE_OWNER = "owner"
ROLE_SUPER = "super_admin"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

VIEW = "view"  # settings page, report
ACT = "act"  # post now, quiz now
EDIT = "edit"  # change schedules and modules
BOARD = "board"  # weekly Top-10

_MATRIX: dict[str, frozenset[str]] = {
    ROLE_OWNER: frozenset({VIEW, ACT, EDIT, BOARD}),
    ROLE_SUPER: frozenset({VIEW, ACT, EDIT, BOARD}),
    ROLE_ADMIN: frozenset({VIEW, ACT, BOARD}),
    ROLE_MEMBER: frozenset({BOARD}),
}


def permits(role: str | None, need: str, *, admins_can_edit: bool = False) -> bool:
    """The whole permission model in one place."""
    if role is None:
        return False
    if role == ROLE_ADMIN and need == EDIT:
        return admins_can_edit
    return need in _MATRIX.get(role, frozenset())


def require_chat(chat: Chat | None, user: User, is_super: bool) -> Chat:
    """Return the chat or raise 404 / 403. Super admins may manage any chat."""
    if chat is None:
        raise PanelError(404, "not_found")
    if not manages(chat, user, is_super):
        raise PanelError(403, "not_owner")
    return chat


class AdminLookup(Protocol):
    enabled: bool

    async def is_admin(self, telegram_chat_id: int, telegram_user_id: int) -> bool: ...

    async def admin_of(self, telegram_chat_ids, telegram_user_id: int) -> set[int]: ...


class Participation(Protocol):
    async def is_participant(self, chat_id: int, user_id: int) -> bool: ...


@dataclass
class OwnerPanel:
    """Thin wrapper around existing services, used by the HTTP layer.

    Every chat lookup goes through `authorize`, which resolves the caller's role
    on the server (database ownership, live Telegram admin list, stored quiz
    answers) and checks it against the permission matrix.
    """

    chats: ChatRepository
    access: AccessService
    profiles: ProfileService
    schedules: ScheduleService
    quiz_launch: QuizLaunch
    leaderboard: LeaderboardService
    is_super: bool
    admins: AdminLookup | None = None
    participation: Participation | None = None
    users: UserRepository | None = None
    _managed: list[tuple[Chat, str]] | None = field(default=None, init=False, repr=False)

    async def list_chats(self, user: User) -> list[Chat]:
        """Chats this user owns."""
        return await self.chats.list_active_for_owner(user.id)

    async def managed(self, user: User) -> list[tuple[Chat, str]]:
        """Owned chats plus active chats where the user is a live Telegram admin."""
        if self._managed is not None:
            return self._managed
        owned = await self.chats.list_active_for_owner(user.id)
        rows: list[tuple[Chat, str]] = [(chat, ROLE_OWNER) for chat in owned]
        if self.admins is not None and getattr(self.admins, "enabled", True):
            others = [chat for chat in await self.chats.list_active() if chat.owner_id != user.id]
            if others:
                ids = await self.admins.admin_of(
                    [chat.telegram_chat_id for chat in others], user.telegram_id
                )
                rows.extend((chat, ROLE_ADMIN) for chat in others if chat.telegram_chat_id in ids)
        self._managed = rows
        return rows

    async def role_in(self, user: User, chat: Chat) -> str | None:
        """Strongest role first; owners never trigger a Telegram call."""
        if chat.owner_id == user.id:
            return ROLE_OWNER
        if self.is_super:
            return ROLE_SUPER
        if (
            self.admins is not None
            and chat.is_active
            and await self.admins.is_admin(chat.telegram_chat_id, user.telegram_id)
        ):
            return ROLE_ADMIN
        if self.participation is not None and await self.participation.is_participant(
            chat.id, user.id
        ):
            return ROLE_MEMBER
        return None

    async def authorize(self, user: User, chat_id: int, need: str) -> tuple[Chat, str]:
        """404 for unknown chats, 403 when the role does not allow `need`."""
        chat = await self.chats.get_by_id(chat_id)
        if chat is None:
            raise PanelError(404, "not_found")
        role = await self.role_in(user, chat)
        if not permits(role, need, admins_can_edit=bool(chat.admins_can_edit)):
            raise PanelError(403, "not_owner")
        return chat, role or ""

    async def load_chat(self, user: User, chat_id: int) -> Chat:
        chat, _role = await self.authorize(user, chat_id, EDIT)
        return chat

    async def detail(self, user: User, chat_id: int) -> dict[str, Any]:
        chat, role = await self.authorize(user, chat_id, VIEW)
        return await self._detail(chat, role)

    async def _detail(self, chat: Chat, role: str) -> dict[str, Any]:
        profile = await self.profiles.get(chat.id)
        daily = await self.schedules.get(chat.id, DAILY)
        quiz = await self.schedules.get(chat.id, QUIZ)
        board = await self.schedules.get(chat.id, LEADERBOARD)
        zone = profile.timezone if profile is not None else "Asia/Tashkent"
        allowed = await self.access.allowed_modules(chat)
        quiz_ok = QUIZ in allowed
        apq_ok = ADMIN_POST_QUIZ in allowed
        board_ok = LEADERBOARD in allowed
        enabled = set(profile.modules_enabled or []) if profile is not None else set()
        can_edit = bool(chat.admins_can_edit)
        return {
            "chat": _chat(chat),
            "access": {
                "role": role,
                "can_edit": permits(role, EDIT, admins_can_edit=can_edit),
                "can_act": permits(role, ACT),
                "can_manage_admins": role in (ROLE_OWNER, ROLE_SUPER),
                "admins_can_edit": can_edit,
            },
            "profile": None if profile is None else _profile(profile),
            "daily": _schedule(daily),
            "quiz": _schedule(quiz),
            "leaderboard": _schedule(board, weekday=True),
            "modules": {
                "quiz": quiz_ok,
                "admin_post_quiz": apq_ok,
                "admin_post_quiz_on": ADMIN_POST_QUIZ in enabled,
                "leaderboard": board_ok,
            },
            "board": await self._board(chat, zone),
        }

    async def board(self, user: User, chat_id: int) -> dict[str, Any]:
        """The live weekly Top-10, plus the caller's own row when they have points."""
        chat, role = await self.authorize(user, chat_id, BOARD)
        profile = await self.profiles.get(chat.id)
        zone = profile.timezone if profile is not None else "Asia/Tashkent"
        return {
            "chat": _chat(chat),
            "role": role,
            "board": await self._board(chat, zone, viewer=user.telegram_id),
        }

    async def _board(self, chat: Chat, zone: str, viewer: int | None = None) -> dict[str, Any]:
        snapshot = await self.leaderboard.live(chat, zone)
        data: dict[str, Any] = {
            "start": snapshot.start.isoformat(),
            "end": snapshot.end.isoformat(),
            "frozen": snapshot.frozen,
            "total": len(snapshot.members),
            "members": [
                {
                    "rank": row.rank,
                    "points": row.score.points,
                    "name": row.full_name or row.username or str(row.telegram_id),
                    **({"me": True} if viewer is not None and row.telegram_id == viewer else {}),
                }
                for row in snapshot.members[:10]
            ],
        }
        if viewer is not None:
            mine = next((row for row in snapshot.members if row.telegram_id == viewer), None)
            if mine is not None:
                data["me"] = {
                    "rank": mine.rank,
                    "points": mine.score.points,
                    "correct": mine.score.correct_count,
                    "answers": mine.score.total_answers,
                }
        return data

    async def update(self, user: User, chat_id: int, body: dict[str, Any]) -> dict[str, Any]:
        chat, role = await self.authorize(user, chat_id, EDIT)
        if "admins_can_edit" in body:
            if role not in (ROLE_OWNER, ROLE_SUPER):
                raise PanelError(403, "owner_only")
            chat.admins_can_edit = bool(body["admins_can_edit"])
        await self._apply_schedule(chat, body, "daily", DAILY)
        if await self.access.is_module_allowed(chat, QUIZ):
            await self._apply_schedule(chat, body, "quiz", QUIZ)
        if await self.access.is_module_allowed(chat, LEADERBOARD):
            # The weekday and the time both switch the schedule on, so the explicit
            # on/off flag must be applied last or "off" would never stick.
            weekday = body.get("board_weekday")
            if weekday is not None:
                try:
                    day = int(weekday)
                except (TypeError, ValueError) as exc:
                    raise PanelError(400, "bad_request") from exc
                if day not in WEEKDAYS:
                    raise PanelError(400, "bad_request")
                await self.schedules.set_weekday(chat, day, LEADERBOARD)
            await self._apply_schedule(chat, body, "leaderboard", LEADERBOARD)
        if "admin_post_quiz" in body:
            await self._toggle_apq(chat, bool(body["admin_post_quiz"]))
        return await self._detail(chat, role)

    async def profile_form(
        self, user: User, chat_id: int, lang: str, default_zone: str
    ) -> dict[str, Any]:
        """The chat profile (wizard answers) plus the allowed choices."""
        chat, role = await self.authorize(user, chat_id, VIEW)
        profile = await self.profiles.get(chat.id)
        data = _profile(profile) if profile is not None else None
        return {
            "chat": _chat(chat),
            "profile": data,
            "default_timezone": default_zone,
            "can_edit": permits(role, EDIT, admins_can_edit=bool(chat.admins_can_edit)),
            "options": profile_options(lang),
        }

    async def save_profile(self, user: User, chat_id: int, body: dict[str, Any]) -> None:
        """Validate and store with the same service the bot wizard uses."""
        chat, _role = await self.authorize(user, chat_id, EDIT)
        fields = (
            "niche_code",
            "niche_description",
            "tone",
            "audience_level",
            "language",
            "timezone",
        )
        if any(not isinstance(body.get(name), str) for name in fields):
            raise PanelError(400, "bad_request")
        raw = ProfileInput(**{name: body[name] for name in fields})
        try:
            await self.profiles.save(await self._owner_of(chat, user), chat.id, raw)
        except ProfileError as exc:
            raise PanelError(400, f"input_{exc.code}") from exc

    async def disconnect(self, user: User, chat_id: int, lifecycle: Any) -> None:
        """Owner (or super admin) only, like the bot's Uzish button."""
        chat, role = await self.authorize(user, chat_id, VIEW)
        if role not in (ROLE_OWNER, ROLE_SUPER):
            raise PanelError(403, "owner_only")
        if not chat.is_active:
            return
        await lifecycle.disconnect(user, chat)

    async def board_now(self, user: User, chat_id: int) -> str:
        """Queue this week's live Top-10, as the bot's "post now" on the board screen."""
        chat, _role = await self.authorize(user, chat_id, ACT)
        if not await self.access.is_module_allowed(chat, LEADERBOARD):
            raise PanelError(403, "module")
        profile = await self.profiles.get(chat.id)
        if profile is None:
            return "profile"
        live = await self.leaderboard.live(chat, profile.timezone)
        if not live.members:
            return "empty"
        return await self.schedules.enqueue_now(
            await self._owner_of(chat, user), chat, LEADERBOARD, extra={"window": "current"}
        )

    async def post_now(self, user: User, chat_id: int) -> str:
        chat, _role = await self.authorize(user, chat_id, ACT)
        return await self.schedules.enqueue_now(await self._owner_of(chat, user), chat, DAILY)

    async def quiz_now(self, user: User, chat_id: int) -> str:
        chat, _role = await self.authorize(user, chat_id, ACT)
        if not await self.access.is_module_allowed(chat, QUIZ):
            raise PanelError(403, "module")
        return await self.quiz_launch.enqueue(await self._owner_of(chat, user), chat)

    async def _owner_of(self, chat: Chat, user: User) -> User:
        """AI quota belongs to the chat owner, whoever presses the button."""
        if chat.owner_id == user.id or self.users is None:
            return user
        owner = await self.users.get_by_id(chat.owner_id)
        if owner is None:
            raise PanelError(404, "not_found")
        return owner

    async def _apply_schedule(
        self, chat: Chat, body: dict[str, Any], prefix: str, module: str
    ) -> None:
        key = "board" if prefix == "leaderboard" else prefix
        time_key = f"{key}_time"
        on_key = f"{key}_enabled"
        if time_key in body and body[time_key] is not None:
            code = _time_code(str(body[time_key]))
            if code is None:
                raise PanelError(400, "bad_request")
            await self.schedules.set_time(chat, code, module)
        if on_key in body and body[on_key] is not None:
            await self.schedules.set_enabled(chat, bool(body[on_key]), module)

    async def _toggle_apq(self, chat: Chat, enabled: bool) -> None:
        if not await self.access.is_module_allowed(chat, ADMIN_POST_QUIZ):
            raise PanelError(403, "module")
        profile = await self.profiles.get(chat.id)
        if profile is None:
            if not enabled:
                return
            raise PanelError(400, "profile")
        await self.profiles.set_module(chat.id, ADMIN_POST_QUIZ, enabled)


# Same order as the bot wizard keyboards.
NICHE_ORDER = ("lang", "biz", "fit", "it", "edu", "news")
TONE_ORDER = ("formal", "friendly", "motiv", "fun")
AUDIENCE_ORDER = ("beginner", "mid", "high", "mixed")
LANGUAGE_ORDER = ("uz", "ru", "en")
assert set(NICHE_ORDER) == PRESET_NICHES and set(TONE_ORDER) == TONES
assert set(AUDIENCE_ORDER) == AUDIENCES and set(LANGUAGE_ORDER) == LANGUAGES


def profile_options(lang: str) -> dict[str, Any]:
    """Wizard choices with the bot's own labels (one source of wording)."""
    from app.i18n import t

    def pick(codes: tuple[str, ...], prefix: str) -> list[dict[str, str]]:
        return [{"code": code, "label": t(f"{prefix}_{code}", lang)} for code in codes]

    return {
        "niches": pick(NICHE_ORDER, "niche"),
        "other": t("niche_other", lang),
        "tones": pick(TONE_ORDER, "tone"),
        "audiences": pick(AUDIENCE_ORDER, "aud"),
        "languages": pick(LANGUAGE_ORDER, "lang"),
        "timezones": sorted(TIMEZONES),
        "niche_max": NICHE_MAX,
        "desc_max": DESC_MAX,
    }


def _time_code(raw: str) -> str | None:
    compact = raw.strip().replace(":", "").replace(".", "")
    if compact.isdigit() and 3 <= len(compact) <= 4:
        compact = compact.zfill(4)
    if parse_clock(compact) is None:
        return None
    return compact


def _chat(chat: Chat) -> dict[str, Any]:
    return {
        "id": chat.id,
        "title": chat.title,
        "type": getattr(chat.type, "value", chat.type),
        "username": chat.username,
        "is_active": chat.is_active,
        "telegram_chat_id": chat.telegram_chat_id,
        "admins_can_edit": bool(chat.admins_can_edit),
    }


def _profile(profile: object) -> dict[str, Any]:
    return {
        "niche_code": getattr(profile, "niche_code", ""),
        "niche_description": getattr(profile, "niche_description", ""),
        "language": getattr(profile, "language", "uz"),
        "tone": getattr(profile, "tone", ""),
        "audience_level": getattr(profile, "audience_level", ""),
        "timezone": getattr(profile, "timezone", "Asia/Tashkent"),
    }


def _schedule(row: object | None, *, weekday: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None
    days = list(getattr(row, "days_of_week", []) or [])
    data: dict[str, Any] = {
        "time": row.time_of_day.strftime("%H:%M"),
        "enabled": bool(row.enabled),
        "days": days,
    }
    if weekday:
        data["weekday"] = days[0] if days else 1
    return data
