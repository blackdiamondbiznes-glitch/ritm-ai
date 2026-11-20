"""Send a prepared quiz the same way Phase 3 does."""

from html import escape

from aiogram import Bot

from app.bot.keyboards.quiz import link_keyboard
from app.bot.poster import ChatGone, RateLimitedSender
from app.db.models.chats import Chat
from app.db.models.content import ContentItem, ContentKind
from app.db.models.quizzes import Quiz
from app.db.models.users import User
from app.db.repositories.content import ContentRepository
from app.db.repositories.quizzes import QuizRepository
from app.db.repositories.usage import UsageRepository
from app.i18n import t
from app.jobs.runner import JobCancel
from app.services.access import AI_METRIC
from app.services.clock import Clock, utcnow
from app.services.lifecycle import ChatLifecycleService
from app.services.quiz_mode import DEEPLINK, delivery_mode
from app.services.quizgen import QuizDraft


class QuizPublisher:
    """Store the quiz, post it, then optionally count one AI generation."""

    def __init__(
        self,
        quizzes: QuizRepository,
        content: ContentRepository,
        usage: UsageRepository,
        sender: RateLimitedSender,
        bot: Bot,
        lifecycle: ChatLifecycleService,
        now: Clock | None = None,
    ) -> None:
        self._quizzes = quizzes
        self._content = content
        self._usage = usage
        self._sender = sender
        self._bot = bot
        self._lifecycle = lifecycle
        self._now = now or utcnow

    async def publish(
        self,
        chat: Chat,
        owner: User,
        lang: str,
        draft: QuizDraft,
        source_id: int,
        *,
        charge: bool = True,
    ) -> Quiz:
        """Post one quiz. Quota is charged only when `charge` is true."""
        mode = delivery_mode(chat.type)
        quiz = await self._quizzes.add(_row(chat.id, source_id, draft, mode))
        message_id, poll_id = await self._send(chat, lang, quiz, draft, mode)
        quiz.telegram_message_id = message_id
        quiz.telegram_poll_id = poll_id
        if charge:
            await self._usage.bump(owner.id, AI_METRIC, self._now().strftime("%Y-%m"))
        await self._content.add(_stored(chat.id, draft, message_id))
        return quiz

    async def charge(self, owner: User) -> None:
        """Count one successful generation after every quiz in a batch is posted."""
        await self._usage.bump(owner.id, AI_METRIC, self._now().strftime("%Y-%m"))

    async def _send(
        self, chat: Chat, lang: str, quiz: Quiz, draft: QuizDraft, mode: str
    ) -> tuple[int, str | None]:
        try:
            if mode == DEEPLINK:
                return await self._link(chat, lang, quiz.id), None
            return await self._sender.poll(
                self._bot,
                chat.telegram_chat_id,
                draft.question,
                list(draft.options),
                draft.correct,
                draft.explanation,
            )
        except ChatGone:
            await self._lifecycle.mark_bot_removed(chat.telegram_chat_id)
            raise JobCancel("gone") from None

    async def _link(self, chat: Chat, lang: str, quiz_id: int) -> int:
        me = await self._bot.get_me()
        if not me.username:
            raise JobCancel("bot")
        url = f"https://t.me/{me.username}?start=quiz_{quiz_id}"
        markup = link_keyboard(lang, url)
        return await self._sender.post(
            self._bot,
            chat.telegram_chat_id,
            escape(t("quiz_channel_post", lang)),
            markup,
        )


def _row(chat_id: int, source_id: int, draft: QuizDraft, mode: str) -> Quiz:
    return Quiz(
        chat_id=chat_id,
        content_item_id=source_id,
        question=draft.question,
        options=list(draft.options),
        correct_index=draft.correct,
        explanation=draft.explanation,
        mode=mode,
    )


def _stored(chat_id: int, draft: QuizDraft, message_id: int) -> ContentItem:
    return ContentItem(
        chat_id=chat_id,
        kind=ContentKind.QUIZ_SOURCE,
        body=draft.question,
        meta={"provider": draft.provider, "model": draft.model},
        telegram_message_id=message_id,
        published_at=utcnow(),
    )
