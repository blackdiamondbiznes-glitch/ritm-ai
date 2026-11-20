"""Chat and profile queries."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chats import Chat, ChatProfile


class ChatRepository:
    """Read and write connected chats."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, chat_id: int) -> Chat | None:
        """Return a chat by primary key."""
        result = await self._session.execute(select(Chat).where(Chat.id == chat_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Chat | None:
        """Return a chat by Telegram id."""
        stmt = select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_owner(self, owner_id: int) -> list[Chat]:
        """Active chats owned by this user, newest first."""
        stmt = (
            select(Chat)
            .where(Chat.owner_id == owner_id, Chat.is_active.is_(True))
            .order_by(Chat.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[Chat]:
        """Every active chat. Used to find chats a user administers in Telegram."""
        stmt = select(Chat).where(Chat.is_active.is_(True)).order_by(Chat.id.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[int]) -> list[Chat]:
        """Chats by primary key, in no particular order."""
        if not ids:
            return []
        result = await self._session.execute(select(Chat).where(Chat.id.in_(ids)))
        return list(result.scalars().all())

    async def count_active(self, owner_id: int) -> int:
        """How many active chats this owner already has."""
        stmt = (
            select(func.count())
            .select_from(Chat)
            .where(Chat.owner_id == owner_id, Chat.is_active.is_(True))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_all(self) -> int:
        """Every chat row, active or not."""
        result = await self._session.execute(select(func.count()).select_from(Chat))
        return int(result.scalar_one())

    async def add(self, chat: Chat) -> Chat:
        """Insert a chat and flush."""
        self._session.add(chat)
        await self._session.flush()
        return chat

    async def deactivate_by_telegram_id(self, telegram_chat_id: int) -> Chat | None:
        """Mark a chat inactive when Telegram says it is gone."""
        chat = await self.get_by_telegram_id(telegram_chat_id)
        if chat is None:
            return None
        chat.is_active = False
        chat.removed_at = datetime.now(UTC)
        await self._session.flush()
        return chat


class ChatProfileRepository:
    """One profile row per chat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int) -> ChatProfile | None:
        """Return the profile or None."""
        stmt = select(ChatProfile).where(ChatProfile.chat_id == chat_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, chat_id: int, fields: dict[str, object]) -> ChatProfile:
        """Create or replace profile fields."""
        row = await self.get(chat_id)
        if row is None:
            row = ChatProfile(chat_id=chat_id, **fields)
            self._session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        await self._session.flush()
        return row
