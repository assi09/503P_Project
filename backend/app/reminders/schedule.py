"""When a reminder is due: pure functions over its schedule, in the person's own time zone.

A schedule is either **once** (a local date and time) or **weekly** (a local time on some days of
the week; all seven is every day). Times are wall-clock times where the person lives, so "22:30 on
weeknights" stays 22:30 across a daylight-saving change. A time that does not exist on the day the
clocks go forward is sent at the same wall-clock reading after the change, once.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # date.weekday() order


class Once(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["once"]
    date: date
    time: time

    @field_validator("time")
    @classmethod
    def _minutes(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0, tzinfo=None)


class Weekly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["weekly"]
    time: time
    weekdays: list[int] = Field(min_length=1, max_length=7)  # 0 is Monday

    @field_validator("time")
    @classmethod
    def _minutes(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0, tzinfo=None)

    @field_validator("weekdays")
    @classmethod
    def _days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays are 0 (Monday) to 6 (Sunday)")
        if len(set(value)) != len(value):
            raise ValueError("each weekday once")
        return sorted(value)


Schedule = Annotated[Once | Weekly, Field(discriminator="kind")]


def zone(name: str) -> ZoneInfo:
    """The time zone by its IANA name; `ValueError` for an unknown one."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone {name!r}") from exc


def _at(day: date, at: time, tz: ZoneInfo) -> datetime:
    """`day` at the wall-clock time `at` in `tz`, as a UTC instant."""
    local = datetime.combine(day, at, tzinfo=tz)
    # A time skipped by a clock change converts to the hour after; round-tripping settles it.
    return local.astimezone(UTC)


def next_due(schedule: Once | Weekly, tz: ZoneInfo, after: datetime) -> datetime | None:
    """The first time strictly after `after` the reminder is due, in UTC; None if never again."""
    if schedule.kind == "once":
        due = _at(schedule.date, schedule.time, tz)
        return due if due > after else None
    today = after.astimezone(tz).date()
    for offset in range(8):  # a week ahead always contains the next chosen weekday
        day = today + timedelta(days=offset)
        if day.weekday() in schedule.weekdays:
            due = _at(day, schedule.time, tz)
            if due > after:
                return due
    return None  # unreachable for a valid schedule


def describe(schedule: Once | Weekly) -> str:
    """The schedule in a few words: "Weeknights at 22:30", "Once, Thu 29 Oct at 07:00"."""
    at = schedule.time.strftime("%H:%M")
    if schedule.kind == "once":
        day = schedule.date
        return f"Once, {WEEKDAYS[day.weekday()]} {day.day} {day.strftime('%b')} at {at}"
    days = set(schedule.weekdays)
    if len(days) == 7:
        return f"Every day at {at}"
    if days == {0, 1, 2, 3, 4}:
        # Evening times read as nights.
        return f"{'Weeknights' if schedule.time >= time(18) else 'Weekdays'} at {at}"
    if days == {5, 6}:
        return f"Weekends at {at}"
    return f"{', '.join(WEEKDAYS[d] for d in sorted(days))} at {at}"
