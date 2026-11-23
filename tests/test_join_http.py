"""The Mini App code box: a link, a prefixed code or a bare code always gets an answer."""

from app.db.models.groups import TutorGroup
from app.i18n import t
from app.webapp.join_routes import parse_code
from tests.test_requests_http import OWNER, PUPIL, _group, client  # noqa: F401


def test_codes_are_read_from_links_and_plain_text() -> None:
    assert parse_code("https://t.me/ritm_airobot?start=join_10c499ea26") == ("join", "10c499ea26")
    assert parse_code("enroll_abcdef1234") == ("enroll", "abcdef1234")
    assert parse_code("  abcdef1234 ") == (None, "abcdef1234")
    assert parse_code("salom!") == (None, None)


async def test_bare_group_code_sends_a_request_and_unknown_code_answers(client) -> None:  # noqa: F811
    http, heads, sessions, bot = client
    group_id = await _group(http, heads)
    async with sessions() as session:
        group = await session.get(TutorGroup, group_id)
        code = group.enroll_code
    sent = await http.post("/api/me/join", headers=heads["pupil"], json={"code": code})
    assert sent.status == 200
    body = await sent.json()
    assert body == {
        "ok": True,
        "kind": "enroll",
        "result": "pending",
        "text": t("enroll_pending", "uz"),
    }
    assert [chat for chat, _text in bot.sent] == [OWNER]
    again = await (
        await http.post("/api/me/join", headers=heads["pupil"], json={"code": code})
    ).json()
    assert again["result"] == "already" and again["ok"] is False
    wrong = await http.post(
        "/api/me/join", headers=heads["pupil"], json={"code": "join_zzzzzz9999"}
    )
    assert (await wrong.json())["text"] == t("join_missing", "uz")
    junk = await (
        await http.post("/api/me/join", headers=heads["pupil"], json={"code": "?"})
    ).json()
    assert junk["result"] == "missing"
    own = await (
        await http.post("/api/me/join", headers=heads["owner"], json={"code": code})
    ).json()
    assert own["result"] == "own"
