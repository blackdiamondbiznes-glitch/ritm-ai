"""Weekly windows and point totals are timezone-safe and use stored correctness."""

from datetime import UTC, datetime

from app.services.scoring import AnswerRow, current_week, previous_week, score_answers


def test_tashkent_week_starts_monday_midnight_local() -> None:
    now = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)  # Friday 19:00 in Tashkent
    week = current_week(now, "Asia/Tashkent")
    assert week.start_date.isoformat() == "2026-11-16"
    assert week.end_date.isoformat() == "2026-11-22"
    assert week.start.utcoffset().total_seconds() == 5 * 3600
    previous = previous_week(now, "Asia/Tashkent")
    assert previous.start_date.isoformat() == "2026-11-09"
    assert previous.end == week.start


def test_answer_near_utc_sunday_follows_the_chat_timezone() -> None:
    week = current_week(datetime(2026, 11, 16, 1, 0, tzinfo=UTC), "Asia/Tashkent")
    # 01:00 UTC Monday is still 06:00 Sunday+5? 01:00 UTC = 06:00 Monday Tashkent.
    assert week.start_date.isoformat() == "2026-11-16"
    late_sunday = datetime(2026, 11, 15, 18, 30, tzinfo=UTC)  # 23:30 Sunday in Tashkent
    early_monday = datetime(2026, 11, 15, 19, 30, tzinfo=UTC)  # 00:30 Monday in Tashkent
    previous = previous_week(early_monday, "Asia/Tashkent")
    assert previous.start <= late_sunday < previous.end
    current = current_week(early_monday, "Asia/Tashkent")
    assert current.start <= early_monday < current.end
    assert late_sunday < current.start


def test_dst_week_still_runs_monday_to_monday() -> None:
    # Europe/London springs forward on 2026-03-29.
    now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    week = current_week(now, "Europe/London")
    assert week.start_date.isoformat() == "2026-03-23"
    assert week.end_date.isoformat() == "2026-03-29"
    assert (week.end - week.start).days == 7


def test_points_only_for_correct_answers_and_tie_break() -> None:
    start = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)
    later = datetime(2026, 11, 16, 7, 0, tzinfo=UTC)
    rows = [
        AnswerRow(1, True, later),
        AnswerRow(1, False, start),
        AnswerRow(2, True, start),
        AnswerRow(2, True, later),
        AnswerRow(3, False, start),
        AnswerRow(3, False, later),
    ]
    scores = score_answers(rows, 10)
    assert [(row.user_id, row.points, row.correct_count, row.total_answers) for row in scores] == [
        (2, 20, 2, 2),
        (1, 10, 1, 2),
        (3, 0, 0, 2),
    ]
    # Same points and same correct count: earlier first correct answer wins.
    tied = score_answers(
        [AnswerRow(8, True, later), AnswerRow(9, True, start)],
        10,
    )
    assert [row.user_id for row in tied] == [9, 8]
