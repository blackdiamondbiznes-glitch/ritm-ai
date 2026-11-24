"""Open a cabinet for an owner. Creating one is idempotent."""

from __future__ import annotations

from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository


class WorkspaceError(Exception):
    """The owner could not be resolved. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WorkspaceService:
    """Find or create the owner's cabinet."""

    def __init__(self, spaces: WorkspaceRepository, users: UserRepository) -> None:
        self._spaces = spaces
        self._users = users

    async def ensure(self, owner: User, vertical: str = "tutor") -> Workspace:
        """Return the cabinet. A second call returns the same row."""
        name = (owner.full_name or "").strip()[:80] or "Kabinet"
        row = await self._spaces.insert_or_get(owner.id, vertical, name)
        await self._spaces.ensure_owner_membership(row.id, owner.id)
        if vertical == "tutor" and owner.cabinet_niche != "tutor":
            owner.cabinet_niche = "tutor"
        return row

    async def id_for(self, owner_id: int, vertical: str = "tutor") -> int:
        """Cabinet id for a new group or card. Missing owners are an error."""
        owner = await self._users.get_by_id(owner_id)
        if owner is None:
            raise WorkspaceError("missing")
        return (await self.ensure(owner, vertical)).id
