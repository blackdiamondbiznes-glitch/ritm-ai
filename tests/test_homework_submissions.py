from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.homework_submissions import (
    HomeworkSubmissionError,
    HomeworkSubmissionService,
)


def _service(*, submissions=None, topics=None, groups=None, students=None):
    return HomeworkSubmissionService(
        submissions or SimpleNamespace(
            get_for=AsyncMock(),
            get=AsyncMock(),
            save=AsyncMock(),
            for_topics=AsyncMock(return_value=[]),
        ),
        topics or SimpleNamespace(
            get=AsyncMock(),
            score=AsyncMock(),
            add_score=AsyncMock(),
            save_score=AsyncMock(),
        ),
        groups or SimpleNamespace(
            active_study=AsyncMock(),
            get_owned=AsyncMock(),
            list_for_owner=AsyncMock(return_value=[]),
        ),
        students or SimpleNamespace(
            by_telegram=AsyncMock(return_value=[]),
            get_owned=AsyncMock(),
            list_for_owner=AsyncMock(return_value=[]),
        ),
    )


@pytest.mark.asyncio
async def test_student_cannot_submit_to_a_group_they_do_not_belong_to():
    topics = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(
        id=5, group_id=9, homework="Read chapter 1",
    )))
    groups = SimpleNamespace(active_study=AsyncMock(return_value=None))
    submissions = SimpleNamespace(get_for=AsyncMock(), save=AsyncMock())
    service = _service(topics=topics, groups=groups, submissions=submissions)

    with pytest.raises(HomeworkSubmissionError, match="missing"):
        await service.submit(SimpleNamespace(id=1, telegram_id=123), 5, "My answer")

    submissions.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_cannot_resubmit_already_graded_homework():
    topic = SimpleNamespace(id=5, group_id=9, homework="Read chapter 1")
    submission = SimpleNamespace(status="graded")
    topics = SimpleNamespace(get=AsyncMock(return_value=topic))
    groups = SimpleNamespace(active_study=AsyncMock(return_value=(
        SimpleNamespace(id=9), SimpleNamespace(id=7),
    )))
    submissions = SimpleNamespace(
        get_for=AsyncMock(return_value=submission),
        save=AsyncMock(),
    )
    service = _service(topics=topics, groups=groups, submissions=submissions)

    with pytest.raises(HomeworkSubmissionError, match="graded"):
        await service.submit(SimpleNamespace(id=1, telegram_id=123), 5, "Updated answer")

    submissions.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_teacher_cannot_grade_submission_for_an_unowned_group():
    row = SimpleNamespace(id=12, topic_id=5, student_id=7, status="submitted")
    topics = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(
        id=5, group_id=9,
    )))
    groups = SimpleNamespace(get_owned=AsyncMock(return_value=None))
    submissions = SimpleNamespace(get=AsyncMock(return_value=row), save=AsyncMock())
    students = SimpleNamespace(get_owned=AsyncMock())
    service = _service(
        submissions=submissions,
        topics=topics,
        groups=groups,
        students=students,
    )

    with pytest.raises(HomeworkSubmissionError, match="missing"):
        await service.grade(2, 12, {"score": 8, "feedback": "Good"})

    students.get_owned.assert_not_awaited()
    submissions.save.assert_not_awaited()
