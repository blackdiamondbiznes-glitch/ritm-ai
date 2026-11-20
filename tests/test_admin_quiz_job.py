"""Publishing quizzes generated from an admin post, with fakes."""

from types import SimpleNamespace

from app.db.models.chats import ChatType
from app.db.models.content import ContentKind
from app.db.models.quizzes import Quiz
from app.jobs.admin_quiz import AdminPostQuizHandler
from app.services.access import AI_METRIC
from app.services.quiz_mode import DEEPLINK, NATIVE
from app.services.quizgen import QuizDraft
from tests.fakes import NOW, World
from tests.test_admin_posts import LONG, _ready


class _Quizzes:
    def __init__(self) -> None:
        self.rows: list[Quiz] = []
        self._seq = 0

    async def add(self, quiz: Quiz) -> Quiz:
        self._seq += 1
        quiz.id = self._seq
        self.rows.append(quiz)
        return quiz

    async def recent_questions(self, chat_id: int, limit: int = 15) -> list[str]:
        return [row.question for row in self.rows if row.chat_id == chat_id][-limit:]


class _Sender:
    def __init__(self) -> None:
        self.posts: list[tuple[int, str]] = []
        self.polls: list[tuple[int, str]] = []
        self._mid = 20

    async def post(self, bot: object, chat_id: int, text: str, markup: object = None) -> int:
        self._mid += 1
        self.posts.append((chat_id, text))
        return self._mid

    async def poll(
        self,
        bot: object,
        chat_id: int,
        question: str,
        options: list[str],
        correct: int,
        explanation: str | None,
    ) -> tuple[int, str]:
        self._mid += 1
        self.polls.append((chat_id, question))
        return self._mid, f"poll-{self._mid}"


class _Generator:
    def __init__(self, drafts: list[QuizDraft]) -> None:
        self.drafts = drafts
        self.calls = 0

    async def draft_from_admin_post(
        self, profile: object, post: str, recent: list[str] | None = None
    ) -> list[QuizDraft]:
        self.calls += 1
        return self.drafts


def _drafts() -> list[QuizDraft]:
    return [
        QuizDraft("Birinchi savol?", ("A", "B", "C"), 0, "A", "gemini", "test"),
        QuizDraft("Ikkinchi savol?", ("X", "Y"), 1, "Y", "gemini", "test"),
    ]


async def _handler(world: World, sender: _Sender, drafts: list[QuizDraft] | None = None):
    item = world.content.rows[0]
    job = world.jobs.rows[0]
    handler = AdminPostQuizHandler(
        world.chats,
        world.users,
        world.profiles,
        world.access,
        world.usage,
        world.content,
        _Quizzes(),
        _Generator(drafts or _drafts()),
        sender,
        SimpleNamespace(get_me=_me),
        world.lifecycle,
    )
    return handler, job, item


async def _me() -> SimpleNamespace:
    return SimpleNamespace(username="ritm_airobot")


async def test_publish_channel_deeplink_and_charges_once() -> None:
    world = await _ready()
    await world.service.ingest(
        telegram_chat_id=-1001, telegram_message_id=11, body=LONG, from_bot=False
    )
    sender = _Sender()
    handler, job, _item = await _handler(world, sender)
    await handler.handle(job)
    assert len(sender.posts) == 2
    assert sender.polls == []
    assert job.payload["published"] == 2
    assert job.payload["charged"] is True
    used = world.usage.counts[(1, AI_METRIC, NOW.strftime("%Y-%m"))]
    assert used == 1
    quiz_sources = [row for row in world.content.rows if row.kind == ContentKind.QUIZ_SOURCE]
    assert len(quiz_sources) == 2


async def test_publish_group_uses_native_poll_and_skips_already_sent() -> None:
    world = await _ready()
    world.chats.rows[0].type = ChatType.SUPERGROUP
    await world.service.ingest(
        telegram_chat_id=-1001, telegram_message_id=11, body=LONG, from_bot=False
    )
    sender = _Sender()
    handler, job, _item = await _handler(world, sender)
    job.payload = {"content_item_id": world.content.rows[0].id, "published": 1}
    await handler.handle(job)
    assert len(sender.polls) == 1
    assert sender.posts == []
    assert job.payload["published"] == 2
    assert world.usage.counts[(1, AI_METRIC, NOW.strftime("%Y-%m"))] == 1


def test_delivery_constants_unchanged() -> None:
    assert DEEPLINK == "private_deeplink"
    assert NATIVE == "group_native"
