"""Sending reminders when they come due: an in-app notification and an email, each exactly once.

`deliver_due` runs every minute inside the API (`loop.py`) and on demand
(`python -m app.reminders deliver`). Each due reminder is handled in its own transaction: its
delivery rows are written first, and their unique key (reminder, due time, channel) means a second
copy of the API running the same minute fails there and sends nothing. Then the next due time is
set, or a one-off is marked done.

What is not sent is still recorded, with why: email turned off, a suggestion in quiet hours or
over the daily cap, or a reminder the server missed by more than `LATE_AFTER` (a wind-down
reminder hours late helps nobody). The person's own reminders ignore quiet hours and the cap:
they chose the time. An email that fails is recorded as failed and not retried; the in-app
notification still arrives.
"""

import html
import logging
import uuid
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Alarm,
    Notification,
    NotificationSetting,
    Reminder,
    ReminderDelivery,
    User,
)
from app.email import Email, Mailer, MailError
from app.reminders import store
from app.reminders.schedule import next_due, zone

logger = logging.getLogger(__name__)

LATE_AFTER = timedelta(minutes=30)
BATCH = 200  # due reminders per pass; the rest wait a minute
Sessions = Callable[[], AbstractContextManager[Session]]


def deliver_due(sessions: Sessions, now: datetime, mailer: Mailer, app_url: str) -> Counter:
    """Sends every reminder due by `now`; returns how many deliveries ended in each status."""
    counts: Counter = Counter()
    with sessions() as db:
        due = list(
            db.scalars(
                select(Reminder.id)
                .where(Reminder.status == "active", Reminder.next_due_at <= now)
                .order_by(Reminder.next_due_at)
                .limit(BATCH)
            )
        )
    for reminder_id in due:
        try:
            with sessions() as db:
                counts.update(_deliver(db, reminder_id, now, mailer, app_url))
        except IntegrityError:
            counts["already_delivered"] += 1  # another copy of the API got there first
    return counts


def _deliver(
    db: Session, reminder_id: uuid.UUID, now: datetime, mailer: Mailer, app_url: str
) -> Counter:
    row = db.scalar(
        select(Reminder)
        .where(
            Reminder.id == reminder_id,
            Reminder.status == "active",
            Reminder.next_due_at <= now,
        )
        .with_for_update(skip_locked=True)  # Postgres; SQLite ignores it
    )
    if row is None:
        return Counter()
    due = store.utc(row.next_due_at)
    user = db.get(User, row.user_id)
    prefs = store.notification_settings(db, user.id)
    held = _held(db, row, user, prefs, due, now)
    deliveries = [
        ReminderDelivery(
            reminder_id=row.id,
            user_id=user.id,
            due_at=due,
            channel=channel,
            status=held or ("skipped_off" if channel == "email" and not prefs.email else "sent"),
            created_at=now,
        )
        for channel in row.channels
    ]
    db.add_all(deliveries)
    db.flush()  # claims every channel before anything leaves the server
    for delivery in deliveries:
        if delivery.status != "sent":
            continue
        if delivery.channel == "in_app":
            db.add(
                Notification(
                    user_id=user.id,
                    kind="reminder",
                    title=row.title,
                    body=row.message or row.title,
                    link="/reminders",
                    reminder_id=row.id,
                    created_at=now,
                )
            )
        else:
            try:
                mailer.send(compose(row, user, app_url))
            except MailError as error:
                delivery.status, delivery.error = "failed", str(error)[:200]
                logger.warning("A reminder email failed: %s", delivery.error)
    counts = Counter(delivery.status for delivery in deliveries)
    # Next time from the later of the due time and now, so a missed one is not sent twice.
    row.next_due_at = next_due(store.schedule_of(row), zone(row.timezone), max(due, now))
    if row.next_due_at is None:
        row.status = "done"
    row.updated_at = now
    return counts


def _held(
    db: Session,
    row: Reminder,
    user: User,
    prefs: NotificationSetting,
    due: datetime,
    now: datetime,
) -> str | None:
    """Why nothing is sent this time, or None."""
    if now - due > LATE_AFTER:
        return "skipped_late"
    if row.source == "person":
        return None
    local = due.astimezone(zone(row.timezone))
    if prefs.quiet_start and _quiet(local.time(), prefs.quiet_start, prefs.quiet_end):
        return "skipped_quiet"
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = suggestions_sent(db, user.id, midnight)
    return "skipped_cap" if sent_today >= prefs.max_per_day else None


def suggestions_sent(db: Session, user_id: uuid.UUID, since: datetime) -> int:
    """Suggested reminders and smart alarms sent since `since`: the daily limit counts both."""
    reminders = db.scalar(
        select(func.count(func.distinct(ReminderDelivery.reminder_id)))
        .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
        .where(
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.status == "sent",
            ReminderDelivery.due_at >= since,
            Reminder.source == "agent",
        )
    )
    alarms = db.scalar(
        select(func.count(Alarm.id)).where(
            Alarm.user_id == user_id, Alarm.status == "sent", Alarm.sent_at >= since
        )
    )
    return reminders + alarms


def _quiet(at: time, start: str, end: str) -> bool:
    """Whether `at` falls in quiet hours, which may run past midnight (22:00 to 07:00)."""
    begin, finish = time.fromisoformat(start), time.fromisoformat(end)
    if begin <= finish:
        return begin <= at < finish
    return at >= begin or at < finish


def compose(row: Reminder, user: User, app_url: str) -> Email:
    """A short, plain email: the reminder, and where to change or stop it."""
    link = f"{app_url.rstrip('/')}/reminders"
    message = row.message or row.title
    text = f"{message}\n\nChange or stop this reminder in Patterns: {link}\n"
    page = (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;color:#1F1A16;'
        'max-width:480px;line-height:1.5">'
        f'<p style="font-size:17px;margin:0 0 16px">{html.escape(message)}</p>'
        f'<p style="font-size:13px;color:#6F655C;margin:0">A reminder you set in Patterns. '
        f'<a href="{html.escape(link)}" style="color:#6F655C">Change or stop it</a>.</p></div>'
    )
    return Email(to=user.email, subject=row.title, text=text, html=page)
