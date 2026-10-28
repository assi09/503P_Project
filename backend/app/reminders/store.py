"""Reminders: create, propose, change and stop them, keeping `next_due_at` right.

Only an active reminder is ever due. The person's own reminders are active at once; one the agent
prepares is `proposed` until the person approves it in the app (decision 10), never by the model.
Every change carries the version the person saw, so two screens cannot overwrite each other.
"""

import uuid
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.sanitize import clean
from app.api.errors import ApiError
from app.config import settings
from app.db.models import NotificationSetting, Reminder, User
from app.reminders.schedule import Once, Schedule, Weekly, next_due, zone

CHANNELS = ("email", "in_app")
SCHEDULE: TypeAdapter[Once | Weekly] = TypeAdapter(Schedule)
# From a status, where the person may take it.
MOVES = {"proposed": {"active", "declined"}, "active": {"paused"}, "paused": {"active"}}
FINAL = {"declined", "cancelled", "done"}


def timezone_of(user: User) -> str:
    return user.timezone or settings.timezone


def schedule_of(row: Reminder) -> Once | Weekly:
    return SCHEDULE.validate_python(row.schedule)


def _due(row: Reminder, now: datetime) -> datetime | None:
    if row.status != "active":
        return None
    return next_due(schedule_of(row), zone(row.timezone), now)


def _text(value: str, limit: int, field: str) -> str:
    text = clean(value, limit)
    if field == "title" and not text:
        raise ApiError(422, "invalid_reminder", "A reminder needs a title.")
    return text


def _channels(channels: list[str]) -> list[str]:
    chosen = [c for c in CHANNELS if c in set(channels)]
    if not chosen or len(set(channels)) != len(chosen):
        raise ApiError(422, "invalid_reminder", "Choose email, in the app, or both.")
    return chosen


def _schedule(schedule: dict | Once | Weekly) -> dict:
    try:
        value = SCHEDULE.validate_python(
            schedule.model_dump() if hasattr(schedule, "model_dump") else schedule
        )
    except ValidationError as exc:
        raise ApiError(422, "invalid_reminder", "That schedule is not valid.") from exc
    return value.model_dump(mode="json")


def _check_future(row: Reminder, now: datetime) -> None:
    if row.status == "active" and row.next_due_at is None:
        raise ApiError(422, "in_the_past", "That time has already passed.")


def create(
    db: Session,
    user: User,
    *,
    title: str,
    message: str,
    schedule: dict | Once | Weekly,
    channels: list[str],
    now: datetime,
    source: str = "person",
    reason: str | None = None,
    evidence_id: str | None = None,
) -> Reminder:
    """The person's own reminder is active at once; the agent's waits as `proposed`."""
    row = Reminder(
        user_id=user.id,
        title=_text(title, 80, "title"),
        message=_text(message, 280, "message"),
        schedule=_schedule(schedule),
        timezone=timezone_of(user),
        channels=_channels(channels),
        status="active" if source == "person" else "proposed",
        source=source,
        reason=clean(reason, 280) or None if reason else None,
        evidence_id=evidence_id,
        created_at=now,
        updated_at=now,
    )
    if (
        row.schedule["kind"] == "once"
        and next_due(schedule_of(row), zone(row.timezone), now) is None
    ):
        raise ApiError(422, "in_the_past", "That time has already passed.")
    row.next_due_at = _due(row, now)
    db.add(row)
    db.flush()
    return row


def get(db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID) -> Reminder:
    row = db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.status != "cancelled",
        )
    )
    if row is None:
        raise ApiError(404, "not_found", "No such reminder.")
    return row


def listing(db: Session, user_id: uuid.UUID) -> list[Reminder]:
    """Everything but cancelled ones, newest first."""
    return list(
        db.scalars(
            select(Reminder)
            .where(Reminder.user_id == user_id, Reminder.status != "cancelled")
            .order_by(Reminder.created_at.desc(), Reminder.id)
            .limit(200)
        )
    )


def change(
    db: Session,
    row: Reminder,
    *,
    version: int,
    now: datetime,
    status: str | None = None,
    title: str | None = None,
    message: str | None = None,
    schedule: dict | Once | Weekly | None = None,
    channels: list[str] | None = None,
) -> Reminder:
    """Approves, pauses, resumes, declines or edits a reminder at the version the person saw."""
    if version != row.version:
        raise ApiError(409, "version_conflict", "This reminder changed; reload and try again.")
    if row.status in FINAL:
        raise ApiError(409, "not_changeable", "This reminder can no longer be changed.")
    if status is not None and status != row.status:
        if status not in MOVES.get(row.status, set()):
            raise ApiError(
                409, "not_changeable", f"A {row.status} reminder cannot become {status}."
            )
        row.status = status
    if title is not None:
        row.title = _text(title, 80, "title")
    if message is not None:
        row.message = _text(message, 280, "message")
    if schedule is not None:
        row.schedule = _schedule(schedule)
    if channels is not None:
        row.channels = _channels(channels)
    row.next_due_at = _due(row, now)
    _check_future(row, now)
    row.version += 1
    row.updated_at = now
    db.flush()
    return row


def cancel(db: Session, row: Reminder, now: datetime) -> None:
    row.status, row.next_due_at, row.updated_at = "cancelled", None, now
    row.version += 1
    db.flush()


def set_timezone(db: Session, user: User, name: str, now: datetime) -> None:
    """Moves the person, and the reminders still to come, to the device's time zone."""
    try:
        zone(name)
    except ValueError as exc:
        raise ApiError(422, "invalid_timezone", "That time zone is not known.") from exc
    if user.timezone == name:
        return
    user.timezone = name
    for row in db.scalars(
        select(Reminder).where(
            Reminder.user_id == user.id, Reminder.status.in_(("proposed", "active", "paused"))
        )
    ):
        row.timezone = name
        row.next_due_at = _due(row, now)
        if row.status == "active" and row.next_due_at is None:
            row.status = "done"  # a one-off whose time has passed in the new zone
        row.updated_at = now
    db.flush()


def notification_settings(db: Session, user_id: uuid.UUID) -> NotificationSetting:
    """The person's settings, or the defaults (not stored until they change something)."""
    return db.get(NotificationSetting, user_id) or NotificationSetting(
        user_id=user_id, quiet_start="22:00", quiet_end="07:00", max_per_day=3, email=True
    )


def save_notification_settings(
    db: Session,
    user_id: uuid.UUID,
    *,
    quiet: tuple[str, str] | None,
    max_per_day: int,
    email: bool,
    now: datetime,
) -> NotificationSetting:
    row = db.get(NotificationSetting, user_id)
    if row is None:
        row = NotificationSetting(user_id=user_id)
        db.add(row)
    row.quiet_start, row.quiet_end = quiet if quiet else (None, None)
    row.max_per_day, row.email, row.updated_at = max_per_day, email, now
    db.flush()
    return row


def utc(value: datetime | None) -> datetime | None:
    """SQLite gives back naive times; they were stored in UTC."""
    if value is None or value.tzinfo:
        return value
    return value.replace(tzinfo=UTC)
