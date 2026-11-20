"""User queries."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User

_UI_LANGS = {"uz", "ru", "en"}


class UserRepository:
    """Read and write users. No plan rules here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Return one user by primary key."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Return one user by Telegram id."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_seen(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
        language_code: str | None,
    ) -> User:
        """Create the user or refresh last_seen. UI language is set only on create."""
        user = await self.get_by_telegram_id(telegram_id)
        now = datetime.now(UTC)
        if user is None:
            lang = language_code if language_code in _UI_LANGS else "uz"
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                language_code=lang,
                last_seen_at=now,
            )
            self._session.add(user)
        else:
            user.username = username
            user.full_name = full_name
            user.last_seen_at = now
        await self._session.flush()
        return user

    async def list_by_ids(self, ids: list[int]) -> list[User]:
        """Return the users that match the given primary keys."""
        if not ids:
            return []
        result = await self._session.execute(select(User).where(User.id.in_(ids)))
        return list(result.scalars().all())

    async def count_founders(self) -> int:
        """Owners already marked as founders."""
        stmt = select(func.count()).select_from(User).where(User.is_founder.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count(self) -> int:
        """Total registered users."""
        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())
