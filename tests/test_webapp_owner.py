"""Non-owners cannot open or change another owner's chat."""

from app.webapp.panel import PanelError, require_chat
from tests.fakes import FakeChats, make_chat, make_user


async def test_non_owner_is_denied_and_super_admin_is_allowed() -> None:
    owner = make_user(1, 100)
    other = make_user(2, 200)
    chats = FakeChats()
    chat = await chats.add(make_chat(owner))
    try:
        require_chat(await chats.get_by_id(chat.id), other, False)
    except PanelError as exc:
        assert exc.status == 403
        assert exc.code == "not_owner"
    else:
        raise AssertionError("not_owner")
    assert require_chat(await chats.get_by_id(chat.id), owner, False) is chat
    assert require_chat(await chats.get_by_id(chat.id), other, True) is chat
    try:
        require_chat(None, owner, True)
    except PanelError as exc:
        assert exc.status == 404
        assert exc.code == "not_found"
    else:
        raise AssertionError("not_found")
