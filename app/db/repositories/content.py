"""Stored content writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.content import ContentItem, ContentKind

_SOURCES = (ContentKind.DAILY, ContentKind.ADMIN_POST)


class ContentRepository:
    """Insert published texts and read the posts a quiz may use."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: ContentItem) -> ContentItem:
        """Insert one content row."""
        self._session.add(item)
        await self._session.flush()
        return item

    async def get(self, item_id: int) -> ContentItem | None:
        """Return one content row by id."""
        stmt = select(ContentItem).where(ContentItem.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(
        self, chat_id: int, telegram_message_id: int
    ) -> ContentItem | None:
        """Return a stored post with this Telegram message id, if any."""
        stmt = select(ContentItem).where(
            ContentItem.chat_id == chat_id,
            ContentItem.telegram_message_id == telegram_message_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def latest(self, chat_id: int, limit: int = 3) -> list[ContentItem]:
        """Newest daily posts and admin posts. Quiz text itself is not a source."""
        stmt = (
            select(ContentItem)
            .where(ContentItem.chat_id == chat_id, ContentItem.kind.in_(_SOURCES))
            .order_by(ContentItem.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def recent_bodies(
        self, chat_id: int, kind: ContentKind = ContentKind.DAILY, limit: int = 15
    ) -> list[str]:
        """Newest published bodies of one kind, used to avoid repeated themes."""
        stmt = (
            select(ContentItem.body)
            .where(ContentItem.chat_id == chat_id, ContentItem.kind == kind)
            .order_by(ContentItem.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]
