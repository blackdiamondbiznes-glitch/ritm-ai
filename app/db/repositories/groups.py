"""Tutor group queries. No validation here."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent


class GroupRepository:
    """Read and write one owner's groups and their members."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(self, owner_id: int) -> list[tuple[TutorGroup, int]]:
        """Groups of this owner, earliest slot first, with a member count."""
        count = func.count(TutorGroupMember.id)
        stmt = (
            select(TutorGroup, count)
            .outerjoin(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .where(TutorGroup.owner_id == owner_id)
            .group_by(TutorGroup.id)
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.desc())
        )
        result = await self._session.execute(stmt)
        return [(row, int(total)) for row, total in result.all()]

    async def get_owned(self, owner_id: int, group_id: int) -> TutorGroup | None:
        """Return the group only when it belongs to this owner."""
        stmt = select(TutorGroup).where(TutorGroup.id == group_id, TutorGroup.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def members(self, group_id: int) -> list[TutorStudent]:
        """Students in this group, by name."""
        stmt = (
            select(TutorStudent)
            .join(TutorGroupMember, TutorGroupMember.student_id == TutorStudent.id)
            .where(TutorGroupMember.group_id == group_id)
            .order_by(TutorStudent.name.asc(), TutorStudent.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def membership(self, group_id: int, student_id: int) -> TutorGroupMember | None:
        """The link between this group and this student, if it exists."""
        stmt = select(TutorGroupMember).where(
            TutorGroupMember.group_id == group_id,
            TutorGroupMember.student_id == student_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, row: TutorGroup) -> TutorGroup:
        """Insert a group and assign its id."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_member(self, row: TutorGroupMember) -> TutorGroupMember:
        """Insert a membership."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: TutorGroup) -> TutorGroup:
        """Flush changes on a group already loaded in this session."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: TutorGroup) -> None:
        """Remove a group. Memberships go with it."""
        await self._session.delete(row)
        await self._session.flush()

    async def studies(self, telegram_id: int) -> bool:
        """True when this Telegram account is a member of at least one group."""
        stmt = (
            select(TutorGroupMember.id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(TutorStudent.telegram_id == telegram_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def groups_for_student(self, student_id: int) -> list[TutorGroup]:
        """Groups this student belongs to."""
        stmt = (
            select(TutorGroup)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .where(TutorGroupMember.student_id == student_id)
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_member(self, row: TutorGroupMember) -> None:
        """Remove a student from a group. The student record stays."""
        await self._session.delete(row)
        await self._session.flush()
