"""Student homework submission reads and writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup
from app.db.models.homework_submissions import TutorHomeworkSubmission
from app.db.models.students import TutorStudent
from app.db.models.topics import TutorTopic


class HomeworkSubmissionRepository:
    """Persistence only; access checks remain in the service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, submission_id: int) -> TutorHomeworkSubmission | None:
        result = await self._session.execute(
            select(TutorHomeworkSubmission).where(TutorHomeworkSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def get_for(self, topic_id: int, student_id: int) -> TutorHomeworkSubmission | None:
        result = await self._session.execute(
            select(TutorHomeworkSubmission).where(
                TutorHomeworkSubmission.topic_id == topic_id,
                TutorHomeworkSubmission.student_id == student_id,
            )
        )
        return result.scalar_one_or_none()

    async def for_topics(self, topic_ids: list[int]) -> list[TutorHomeworkSubmission]:
        if not topic_ids:
            return []
        result = await self._session.execute(
            select(TutorHomeworkSubmission)
            .where(TutorHomeworkSubmission.topic_id.in_(topic_ids))
            .order_by(TutorHomeworkSubmission.submitted_at.desc())
        )
        return list(result.scalars().all())

    async def for_owner(self, owner_id: int) -> list[tuple]:
        stmt = (
            select(TutorHomeworkSubmission, TutorTopic, TutorGroup, TutorStudent)
            .join(TutorTopic, TutorTopic.id == TutorHomeworkSubmission.topic_id)
            .join(TutorGroup, TutorGroup.id == TutorTopic.group_id)
            .join(TutorStudent, TutorStudent.id == TutorHomeworkSubmission.student_id)
            .where(TutorGroup.owner_id == owner_id, TutorTopic.homework.is_not(None))
            .order_by(TutorHomeworkSubmission.submitted_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def save(self, row: TutorHomeworkSubmission) -> TutorHomeworkSubmission:
        self._session.add(row)
        await self._session.flush()
        return row
