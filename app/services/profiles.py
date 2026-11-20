"""Profile wizard validation and storage."""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models.chats import ChatProfile
from app.db.models.users import User
from app.db.repositories.chats import ChatProfileRepository
from app.services.access import AccessService

PRESET_NICHES = frozenset({"lang", "biz", "fit", "it", "edu", "news"})
TONES = frozenset({"formal", "friendly", "motiv", "fun"})
AUDIENCES = frozenset({"beginner", "mid", "high", "mixed"})
LANGUAGES = frozenset({"uz", "ru", "en"})
TIMEZONES = frozenset(
    {
        "Asia/Tashkent",
        "Asia/Almaty",
        "Asia/Dubai",
        "Europe/Moscow",
        "Europe/Istanbul",
        "UTC",
    }
)
NICHE_MAX = 200
DESC_MAX = 500


class ProfileError(Exception):
    """Invalid profile input. `code` is `empty`, `long` or `choice`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProfileInput:
    """Validated profile fields."""

    niche_code: str
    niche_description: str
    tone: str
    audience_level: str
    language: str
    timezone: str


class ProfileService:
    """Stores a chat profile. Modules mirror the effective plan."""

    def __init__(self, profiles: ChatProfileRepository, access: AccessService) -> None:
        self._profiles = profiles
        self._access = access

    async def get(self, chat_id: int) -> ChatProfile | None:
        """Return the saved profile."""
        return await self._profiles.get(chat_id)

    async def set_module(self, chat_id: int, module: str, enabled: bool) -> ChatProfile | None:
        """Turn one module on or off. Missing profiles stay missing."""
        profile = await self._profiles.get(chat_id)
        if profile is None:
            return None
        current = list(profile.modules_enabled or [])
        if enabled and module not in current:
            current.append(module)
        if not enabled:
            current = [item for item in current if item != module]
        return await self._profiles.upsert(
            chat_id,
            {"modules_enabled": current, "updated_at": datetime.now(UTC)},
        )

    async def save(self, owner: User, chat_id: int, raw: ProfileInput) -> ChatProfile:
        """Validate and upsert. Raises ProfileError on bad input."""
        clean = validate_profile(raw)
        existing = await self._profiles.get(chat_id)
        if existing is not None:
            # Editing keeps the owner's module switches (e.g. post quizzes turned off).
            modules = list(existing.modules_enabled or [])
        else:
            plan = await self._access.get_effective_plan(owner)
            modules = list(plan.modules or [])
        return await self._profiles.upsert(
            chat_id,
            {
                "niche_code": clean.niche_code,
                "niche_description": clean.niche_description,
                "tone": clean.tone,
                "audience_level": clean.audience_level,
                "language": clean.language,
                "timezone": clean.timezone,
                "modules_enabled": modules,
                "updated_at": datetime.now(UTC),
            },
        )


def validate_profile(raw: ProfileInput) -> ProfileInput:
    """Check lengths and allowed choices."""
    niche = raw.niche_code.strip()
    if not niche:
        raise ProfileError("empty")
    if len(niche) > NICHE_MAX:
        raise ProfileError("long")
    description = raw.niche_description.strip()
    if not description:
        raise ProfileError("empty")
    if len(description) > DESC_MAX:
        raise ProfileError("long")
    if raw.tone not in TONES or raw.audience_level not in AUDIENCES:
        raise ProfileError("choice")
    if raw.language not in LANGUAGES or raw.timezone not in TIMEZONES:
        raise ProfileError("choice")
    return ProfileInput(
        niche_code=niche,
        niche_description=description,
        tone=raw.tone,
        audience_level=raw.audience_level,
        language=raw.language,
        timezone=raw.timezone,
    )
