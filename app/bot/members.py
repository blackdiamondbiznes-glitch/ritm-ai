"""Pure checks on Telegram chat-member objects."""

from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMember


def user_is_manager(member: ChatMember) -> bool:
    """Creator or administrator. A regular member cannot connect the chat."""
    return member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}


def bot_can_post(member: ChatMember) -> bool:
    """Admin with permission to post. `None` means the flag does not apply (groups)."""
    if member.status == ChatMemberStatus.CREATOR:
        return True
    if member.status != ChatMemberStatus.ADMINISTRATOR:
        return False
    flag = getattr(member, "can_post_messages", None)
    return flag is not False


def is_promoted(old: ChatMemberStatus, new: ChatMemberStatus) -> bool:
    """True only on the transition into admin, not on later rights edits."""
    admin = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    return new in admin and old not in admin


def is_removed(old: ChatMemberStatus, new: ChatMemberStatus) -> bool:
    """Left, kicked, or demoted from admin."""
    admin = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    if new in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        return True
    return old in admin and new not in admin


def map_chat_type(kind: ChatType) -> str:
    """Map aiogram chat types onto our enum values."""
    if kind == ChatType.CHANNEL:
        return "channel"
    if kind == ChatType.SUPERGROUP:
        return "supergroup"
    return "group"
