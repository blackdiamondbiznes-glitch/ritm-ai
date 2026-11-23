"""Store and look up widget messages by kind and ref."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.widget_messages import WidgetMessage


class WidgetMessageRepository:
    """Upsert the last message id for a card."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(self, kind: str, ref_id: int, telegram_id: int, message_id: int) -> None:
        """Insert or replace the stored message coordinates."""
        stmt = insert(WidgetMessage).values(
            kind=kind, ref_id=ref_id, telegram_id=telegram_id, message_id=message_id
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tutor_widget_messages_ref",
            set_={"message_id": message_id},
        )
        await self._session.execute(stmt)

    async def find(self, kind: str, ref_id: int) -> list[WidgetMessage]:
        """Every chat that still has this card."""
        stmt = select(WidgetMessage).where(
            WidgetMessage.kind == kind, WidgetMessage.ref_id == ref_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def one(self, kind: str, ref_id: int, telegram_id: int) -> WidgetMessage | None:
        """The card in one private chat, if we sent it."""
        stmt = select(WidgetMessage).where(
            WidgetMessage.kind == kind,
            WidgetMessage.ref_id == ref_id,
            WidgetMessage.telegram_id == telegram_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def by_message(self, telegram_id: int, message_id: int) -> WidgetMessage | None:
        """The card sent as this message, if we stored it."""
        stmt = select(WidgetMessage).where(
            WidgetMessage.telegram_id == telegram_id,
            WidgetMessage.message_id == message_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
