"""Workspace queries. No validation here."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup
from app.db.models.students import TutorStudent
from app.db.models.workspaces import Workspace


class WorkspaceRepository:
    """Read and write one owner's cabinets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_vertical(self, vertical: str) -> list[Workspace]:
        """Every cabinet of this vertical, oldest first."""
        stmt = select(Workspace).where(Workspace.vertical == vertical).order_by(Workspace.id.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def by_owner_vertical(self, owner_id: int, vertical: str) -> Workspace | None:
        """The cabinet for this owner and vertical, if it exists."""
        stmt = select(Workspace).where(
            Workspace.owner_id == owner_id, Workspace.vertical == vertical
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def insert_or_get(self, owner_id: int, vertical: str, name: str) -> Workspace:
        """Insert the cabinet, or return the one that won the race."""
        stmt = (
            pg_insert(Workspace)
            .values(owner_id=owner_id, vertical=vertical, name=name)
            .on_conflict_do_nothing(constraint="uq_workspaces_owner_vertical")
            .returning(Workspace.id)
        )
        new_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if new_id is not None:
            loaded = await self._session.get(Workspace, new_id)
            if loaded is None:
                raise RuntimeError("workspace insert missed")
            return loaded
        found = await self.by_owner_vertical(owner_id, vertical)
        if found is None:
            raise RuntimeError("workspace insert missed")
        return found

    async def teaching_for(self, owner_id: int) -> list[tuple[Workspace, int, int]]:
        """Each cabinet with its group count and visible student count."""
        groups = (
            select(func.count(TutorGroup.id))
            .where(TutorGroup.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        students = (
            select(func.count(TutorStudent.id))
            .where(
                TutorStudent.workspace_id == Workspace.id,
                TutorStudent.status != "pending",
            )
            .correlate(Workspace)
            .scalar_subquery()
        )
        stmt = (
            select(Workspace, groups, students)
            .where(Workspace.owner_id == owner_id)
            .order_by(Workspace.id.asc())
        )
        result = await self._session.execute(stmt)
        return [
            (space, int(group_count), int(student_count))
            for space, group_count, student_count in result.all()
        ]
