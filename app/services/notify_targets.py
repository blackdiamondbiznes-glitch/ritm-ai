"""Who receives a group notice: linked students and the linked chat."""

from __future__ import annotations

from app.db.models.groups import TutorGroup
from app.db.models.students import TutorStudent
from app.db.repositories.chats import ChatRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.users import UserRepository
from app.services.notify_rules import language

_SKIP = frozenset({"inactive", "pending"})


async def linked_chat(chats: ChatRepository, group: TutorGroup):
    """The active chat this owner linked, or nothing."""
    if group.chat_id is None:
        return None
    chat = await chats.get_by_id(group.chat_id)
    if chat is None or not chat.is_active or chat.owner_id != group.owner_id:
        return None
    return chat


async def student_dest(users: UserRepository, student: TutorStudent) -> dict | None:
    """A private chat for an active student who linked Telegram."""
    if student.status in _SKIP or not student.telegram_id:
        return None
    telegram_id = int(student.telegram_id)
    person = await users.get_by_telegram_id(telegram_id)
    return {
        "target": "student",
        "target_id": telegram_id,
        "telegram_id": telegram_id,
        "lang": language(person.language_code if person else None),
    }


async def group_dest(
    chats: ChatRepository, users: UserRepository, group: TutorGroup
) -> dict | None:
    """The group chat, written in the teacher's language."""
    chat = await linked_chat(chats, group)
    if chat is None:
        return None
    owner = await users.get_by_id(group.owner_id)
    return {
        "target": "group",
        "target_id": int(chat.telegram_chat_id),
        "telegram_id": int(chat.telegram_chat_id),
        "lang": language(owner.language_code if owner else None),
    }


async def audience(
    groups: GroupRepository, chats: ChatRepository, users: UserRepository, group: TutorGroup
) -> list[dict]:
    """Active linked students, then the group chat when one is linked."""
    found: list[dict] = []
    for student in await groups.members(group.id):
        dest = await student_dest(users, student)
        if dest is not None:
            found.append(dest)
    chat = await group_dest(chats, users, group)
    if chat is not None:
        found.append(chat)
    return found
