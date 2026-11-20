"""Queue a quiz only when the chat already has a published post."""

from app.db.models.chats import Chat
from app.db.models.users import User
from app.db.repositories.content import ContentRepository
from app.services.quiz_mode import QUIZ
from app.services.schedule import ScheduleService


class QuizLaunch:
    """The button path. The tick still re-checks before it spends quota."""

    def __init__(self, schedules: ScheduleService, content: ContentRepository) -> None:
        self._schedules = schedules
        self._content = content

    async def enqueue(self, owner: User, chat: Chat) -> str:
        """Return a locale code, including content when nothing has been published."""
        if not await self._content.latest(chat.id):
            return "content"
        return await self._schedules.enqueue_now(owner, chat, QUIZ)
