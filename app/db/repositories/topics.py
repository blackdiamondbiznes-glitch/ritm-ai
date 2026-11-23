"""Topic and score queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.topics import TutorScore, TutorTopic


class TopicRepository:
    """Read and write topics and their marks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_groups(self, group_ids: list[int]) -> list[TutorTopic]:
        """Topics for several groups. Empty input does not hit the database."""
        if not group_ids:
            return []
        stmt = (
            select(TutorTopic)
            .where(TutorTopic.group_id.in_(group_ids))
            .order_by(TutorTopic.held_on.asc(), TutorTopic.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_group(self, group_id: int) -> list[TutorTopic]:
        """Newest lesson day first."""
        stmt = (
            select(TutorTopic)
            .where(TutorTopic.group_id == group_id)
            .order_by(TutorTopic.held_on.desc(), TutorTopic.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, topic_id: int) -> TutorTopic | None:
        """One topic by id."""
        result = await self._session.execute(select(TutorTopic).where(TutorTopic.id == topic_id))
        return result.scalar_one_or_none()

    async def scores_for(self, topic_ids: list[int]) -> list[TutorScore]:
        """Every mark on these topics."""
        if not topic_ids:
            return []
        stmt = select(TutorScore).where(TutorScore.topic_id.in_(topic_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def score(self, topic_id: int, student_id: int) -> TutorScore | None:
        """The mark for one student on one topic."""
        stmt = select(TutorScore).where(
            TutorScore.topic_id == topic_id, TutorScore.student_id == student_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_topic(self, row: TutorTopic) -> TutorTopic:
        """Insert a topic and assign its id."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_score(self, row: TutorScore) -> TutorScore:
        """Insert a mark."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def save_score(self, row: TutorScore) -> TutorScore:
        """Flush a changed mark."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete_score(self, row: TutorScore) -> None:
        """Remove a mark so the student is ungraded again."""
        await self._session.delete(row)
        await self._session.flush()
