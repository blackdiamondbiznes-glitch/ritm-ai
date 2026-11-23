"""Tutor group queries. No validation here."""

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User


class GroupRepository:
    """Read and write one owner's groups and their members."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(self, owner_id: int) -> list[tuple[TutorGroup, int]]:
        """Groups of this owner, earliest slot first, with a member count."""
        count = func.count(TutorGroupMember.id)
        stmt = (
            select(TutorGroup, count)
            .outerjoin(
                TutorGroupMember,
                and_(
                    TutorGroupMember.group_id == TutorGroup.id,
                    TutorGroupMember.status == "active",
                ),
            )
            .where(TutorGroup.owner_id == owner_id)
            .group_by(TutorGroup.id)
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.desc())
        )
        result = await self._session.execute(stmt)
        return [(row, int(total)) for row, total in result.all()]

    async def by_enroll_code(self, code: str) -> TutorGroup | None:
        """The group opened by this public registration code."""
        stmt = select(TutorGroup).where(TutorGroup.enroll_code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get(self, group_id: int) -> TutorGroup | None:
        """The group by id, for internal jobs that already know the id."""
        return await self._session.get(TutorGroup, group_id)

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
            .where(
                TutorGroupMember.group_id == group_id,
                TutorGroupMember.status == "active",
            )
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

    async def add_member_once(self, group_id: int, student_id: int, status: str) -> bool:
        """Insert a membership unless this pair already exists."""
        stmt = (
            pg_insert(TutorGroupMember)
            .values(group_id=group_id, student_id=student_id, status=status)
            .on_conflict_do_nothing(constraint="uq_tutor_group_members")
            .returning(TutorGroupMember.id)
        )
        created = (await self._session.execute(stmt)).scalar_one_or_none()
        return created is not None

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
            .where(
                TutorStudent.telegram_id == telegram_id,
                TutorGroupMember.status == "active",
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def groups_for_student(self, student_id: int) -> list[TutorGroup]:
        """Groups this student belongs to."""
        stmt = (
            select(TutorGroup)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .where(
                TutorGroupMember.student_id == student_id,
                TutorGroupMember.status == "active",
            )
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_member(self, row: TutorGroupMember) -> None:
        """Remove a student from a group. The student record stays."""
        await self._session.delete(row)
        await self._session.flush()

    async def save_member(self, row: TutorGroupMember) -> TutorGroupMember:
        """Flush a membership that is already loaded."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def count_for_owner(self, owner_id: int) -> int:
        """How many groups this owner has."""
        stmt = select(func.count()).select_from(TutorGroup).where(TutorGroup.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_pending_for_owner(self, owner_id: int) -> int:
        """Registration requests still waiting for this owner."""
        stmt = (
            select(func.count())
            .select_from(TutorGroupMember)
            .join(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .where(TutorGroup.owner_id == owner_id, TutorGroupMember.status == "pending")
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def pending_for_owner(
        self, owner_id: int
    ) -> list[tuple[TutorGroupMember, TutorGroup, TutorStudent]]:
        """Requests newest last, so the teacher sees the oldest first."""
        stmt = (
            select(TutorGroupMember, TutorGroup, TutorStudent)
            .join(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(TutorGroup.owner_id == owner_id, TutorGroupMember.status == "pending")
            .order_by(TutorGroupMember.created_at.asc(), TutorGroupMember.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(member, group, student) for member, group, student in result.all()]

    async def memberships_for_student(self, student_id: int) -> list[TutorGroupMember]:
        """Every membership of this card, including ones still waiting."""
        stmt = select(TutorGroupMember).where(TutorGroupMember.student_id == student_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def active_for_students(self, student_ids: list[int]) -> list[tuple[TutorGroup, int]]:
        """Active groups for these cards, as (group, student id)."""
        if not student_ids:
            return []
        stmt = (
            select(TutorGroup, TutorGroupMember.student_id)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .where(
                TutorGroupMember.student_id.in_(student_ids),
                TutorGroupMember.status == "active",
            )
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(group, int(student_id)) for group, student_id in result.all()]

    async def study_for(self, telegram_id: int, skip_owner_id: int) -> list[tuple]:
        """Classes this account studies in, except the ones they teach."""
        stmt = (
            select(
                TutorGroup.id,
                TutorGroup.name,
                TutorGroup.level,
                User.full_name,
                TutorGroup.workspace_id,
                TutorGroupMember.status,
            )
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .join(User, User.id == TutorGroup.owner_id)
            .where(
                TutorStudent.telegram_id == telegram_id,
                TutorGroup.owner_id != skip_owner_id,
                TutorGroupMember.status.in_(("active", "pending")),
            )
            .order_by(TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def all_groups(self) -> list[TutorGroup]:
        """Every group, oldest first. The daily fill walks this list."""
        result = await self._session.execute(select(TutorGroup).order_by(TutorGroup.id.asc()))
        return list(result.scalars().all())

    async def active_members(self, group_ids: list[int]) -> list[tuple[int, TutorStudent]]:
        """Active students in these groups, as (group id, student)."""
        if not group_ids:
            return []
        stmt = (
            select(TutorGroupMember.group_id, TutorStudent)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(
                TutorGroupMember.group_id.in_(group_ids),
                TutorGroupMember.status == "active",
            )
            .order_by(TutorStudent.name.asc(), TutorStudent.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(int(group_id), student) for group_id, student in result.all()]

    async def active_study(
        self, telegram_id: int, group_id: int, skip_owner_id: int
    ) -> tuple[TutorGroup, TutorStudent] | None:
        """The group and card when this account is an active member and not the teacher."""
        stmt = (
            select(TutorGroup, TutorStudent)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(
                TutorGroup.id == group_id,
                TutorStudent.telegram_id == telegram_id,
                TutorGroup.owner_id != skip_owner_id,
                TutorGroupMember.status == "active",
            )
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        group, student = row
        return group, student
