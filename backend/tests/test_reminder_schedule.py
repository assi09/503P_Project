from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from app.reminders.schedule import Once, Weekly, describe, next_due, zone

BEIRUT = zone("Asia/Beirut")
LONDON = zone("Europe/London")


def weekly(at: str, days: list[int]) -> Weekly:
    return Weekly(kind="weekly", time=time.fromisoformat(at), weekdays=days)


def local(tz, *parts) -> datetime:
    return datetime(*parts, tzinfo=tz).astimezone(UTC)


def test_a_daily_reminder_is_due_later_today_or_tomorrow():
    every_day = weekly("22:30", list(range(7)))
    morning = local(BEIRUT, 2026, 10, 28, 9, 0)
    assert next_due(every_day, BEIRUT, morning) == local(BEIRUT, 2026, 10, 28, 22, 30)
    # Exactly at the time it is not due again until the next day.
    at = local(BEIRUT, 2026, 10, 28, 22, 30)
    assert next_due(every_day, BEIRUT, at) == local(BEIRUT, 2026, 10, 29, 22, 30)


def test_weeknights_skip_the_weekend():
    nights = weekly("22:30", [0, 1, 2, 3, 4])
    friday_late = local(BEIRUT, 2026, 10, 30, 23, 0)  # a Friday
    assert next_due(nights, BEIRUT, friday_late) == local(BEIRUT, 2026, 11, 2, 22, 30)  # Monday


def test_the_wall_clock_time_holds_across_a_daylight_saving_change():
    # London leaves summer time on Sunday 2026-10-25: 07:00 stays 07:00 locally.
    every_day = weekly("07:00", list(range(7)))
    before = next_due(every_day, LONDON, local(LONDON, 2026, 10, 23, 8, 0))  # due Sat 24th
    after = next_due(every_day, LONDON, before)
    assert before.astimezone(LONDON).time() == after.astimezone(LONDON).time() == time(7)
    assert after - before == timedelta(hours=25)


def test_a_time_skipped_by_the_clocks_going_forward_is_still_sent_once():
    # London skips 01:00-02:00 on Sunday 2026-03-29.
    every_day = weekly("01:30", list(range(7)))
    saturday = local(LONDON, 2026, 3, 28, 12, 0)
    due = next_due(every_day, LONDON, saturday)
    assert due.astimezone(LONDON).date() == date(2026, 3, 29)
    following = next_due(every_day, LONDON, due)
    assert following.astimezone(LONDON).date() == date(2026, 3, 30)


def test_a_one_off_is_due_once_and_never_in_the_past():
    once = Once(kind="once", date=date(2026, 10, 29), time=time(7, 0))
    now = local(BEIRUT, 2026, 10, 28, 20, 0)
    due = next_due(once, BEIRUT, now)
    assert due == local(BEIRUT, 2026, 10, 29, 7, 0)
    assert next_due(once, BEIRUT, due) is None


@pytest.mark.parametrize(
    "days, at, text",
    [
        (list(range(7)), "07:00", "Every day at 07:00"),
        ([0, 1, 2, 3, 4], "22:30", "Weeknights at 22:30"),
        ([0, 1, 2, 3, 4], "08:15", "Weekdays at 08:15"),
        ([5, 6], "10:00", "Weekends at 10:00"),
        ([4, 0, 2], "18:00", "Mon, Wed, Fri at 18:00"),
    ],
)
def test_schedules_read_in_a_few_words(days, at, text):
    assert describe(weekly(at, days)) == text


def test_a_one_off_reads_with_its_day():
    assert describe(Once(kind="once", date=date(2026, 10, 29), time=time(7))) == (
        "Once, Thu 29 Oct at 07:00"
    )


@pytest.mark.parametrize("days", [[], [7], [-1], [1, 1], list(range(8))])
def test_bad_weekdays_are_refused(days):
    with pytest.raises(ValidationError):
        Weekly(kind="weekly", time=time(8), weekdays=days)


def test_seconds_are_dropped_and_unknown_zones_refused():
    assert weekly("08:00:59", [0]).time == time(8)
    with pytest.raises(ValueError, match="unknown time zone"):
        zone("Mars/Olympus")
