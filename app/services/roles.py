"""Teaching and learning are computed from rows. Nothing is stored on the user."""

from __future__ import annotations

from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.workspaces import WorkspaceRepository


class RoleService:
    """What this Telegram account teaches and where it studies."""

    def __init__(self, spaces: WorkspaceRepository, groups: GroupRepository) -> None:
        self._spaces = spaces
        self._groups = groups

    async def for_user(self, user: User) -> dict:
        """Teaching cabinets, active classes, and requests still waiting."""
        teaching = [
            {
                "workspace_id": space.id,
                "vertical": space.vertical,
                "name": space.name,
                "groups": groups,
                "students": students,
            }
            for space, groups, students in await self._spaces.teaching_for(user.id)
        ]
        learning: list[dict] = []
        pending: list[dict] = []
        for row in await self._groups.study_for(user.telegram_id, user.id):
            item = {
                "group_id": row[0],
                "group_name": row[1],
                "level": row[2],
                "teacher_name": row[3] or "",
                "workspace_id": row[4],
            }
            if row[5] == "pending":
                pending.append(item)
            else:
                learning.append(item)
        return {"teaching": teaching, "learning": learning, "pending": pending}
