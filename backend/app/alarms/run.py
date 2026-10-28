"""Checking each person for smart alarms, and sending them.

`check` runs the detectors on the person's data and stores what is new as `pending`: a candidate
is new unless an alarm with the same key (the same kind about the same metric) was raised within
its cooldown, so a bad week does not ring every hour. Its evidence is stored too, so the alarm
links to its numbers. `deliver` sends pending alarms in the app and by email, outside quiet hours
and under the person's daily limit (shared with the agent's suggested reminders), strongest
first; one that waited `EXPIRE_AFTER` is dropped, since news that old is no longer news.

The text here is a fixed template built from the evidence; the agent's explanation replaces it
when it passes its checks (`explain.py`, next).
"""

import html
import logging
import uuid
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.present import format_level, label, short_date
from app.alarms.detect import KINDS, Candidate, detect
from app.analysis.day import with_scores
from app.db.chat import store_evidence
from app.db.daily import load_daily
from app.db.models import Alarm, AlarmSetting, GoogleConnection, Notification, User
from app.email import Email, Mailer, MailError
from app.reminders import store
from app.reminders.deliver import _quiet, suggestions_sent
from app.reminders.schedule import zone

logger = logging.getLogger(__name__)

COOLDOWN = {
    "day": timedelta(days=3),
    "streak": timedelta(days=3),
    "finding": timedelta(days=7),
    "data": timedelta(days=2),
}
EXPIRE_AFTER = timedelta(hours=12)
SOURCE = "google_health"
Sessions = Callable[[], AbstractContextManager[Session]]


def settings_of(db: Session, user_id: uuid.UUID) -> AlarmSetting:
    return db.get(AlarmSetting, user_id) or AlarmSetting(
        user_id=user_id, enabled=True, muted_kinds=[], sensitivity="normal"
    )


def save_settings(
    db: Session,
    user_id: uuid.UUID,
    *,
    enabled: bool,
    muted_kinds: list[str],
    sensitivity: str,
    now: datetime,
) -> AlarmSetting:
    row = db.get(AlarmSetting, user_id)
    if row is None:
        row = AlarmSetting(user_id=user_id)
        db.add(row)
    row.enabled, row.sensitivity, row.updated_at = enabled, sensitivity, now
    row.muted_kinds = [k for k in KINDS if k in set(muted_kinds)]
    db.flush()
    return row


def _side(direction: str | None) -> str:
    return "below" if direction == "down" else "above"


def text(candidate: Candidate) -> tuple[str, str]:
    """The alarm in plain words, every number from its evidence; no advice, no causes."""
    if candidate.kind == "data":
        if candidate.metric == "reconnect":
            return (
                "Reconnect Google Health",
                "Google's sign-in for Patterns expired, so new days are not coming in. "
                "Reconnect it in Settings.",
            )
        return (
            "No new data for two days",
            "Patterns has not received new Fitbit data for two days. Syncing the Fitbit app "
            "on your phone brings it in.",
        )
    metric = candidate.metric
    name = label(metric)
    side = _side(candidate.direction)
    first = candidate.evidence[0].stats
    usual = (
        f"{format_level(metric, first['usual_low'])}–{format_level(metric, first['usual_high'])}"
    )
    if candidate.kind == "day":
        return (
            f"{name[0].upper()}{name[1:]} well {side} your usual",
            f"{short_date(candidate.day)}: {format_level(metric, first['value'])}, against your "
            f"usual {usual}.",
        )
    if candidate.kind == "streak":
        days = len(candidate.evidence)
        return (
            f"{name[0].upper()}{name[1:]} {side} usual {days} days running",
            f"Each of the last {days} days was {side} your usual {usual}.",
        )
    moved = "dropped" if candidate.direction == "down" else "risen"
    return (
        f"{name[0].upper()}{name[1:]} has {moved} over two weeks",
        f"The last 14 days averaged {format_level(metric, first['mean_recent'])}, against "
        f"{format_level(metric, first['mean_baseline'])} in the four weeks before.",
    )


def link(alarm: Alarm) -> str:
    if alarm.kind == "data":
        return "/settings"
    return f"/evidence/{alarm.evidence_ids[0]}" if alarm.evidence_ids else "/"


def check(
    db: Session, user: User, now: datetime, frame, reconnect_needed: bool = False
) -> list[Alarm]:
    """Stores the person's new alarms as pending; returns them."""
    prefs = settings_of(db, user.id)
    if not prefs.enabled:
        return []
    today = now.astimezone(zone(store.timezone_of(user))).date()
    kinds = tuple(k for k in KINDS if k not in (prefs.muted_kinds or []))
    created = []
    for candidate in detect(
        frame,
        today,
        sensitivity=prefs.sensitivity,
        reconnect_needed=reconnect_needed,
        kinds=kinds,
    ):
        since = now - COOLDOWN[candidate.kind]
        recent = db.scalar(
            select(Alarm.id).where(
                Alarm.user_id == user.id, Alarm.key == candidate.key, Alarm.created_at >= since
            )
        )
        if recent is not None:
            continue
        cited = {e.id for e in candidate.evidence}
        store_evidence(db, user.id, None, candidate.evidence, cited)
        title, body = text(candidate)
        alarm = Alarm(
            user_id=user.id,
            kind=candidate.kind,
            metric=candidate.metric,
            key=candidate.key,
            day=candidate.day,
            severity=round(candidate.severity, 3),
            evidence_ids=sorted(cited),
            title=title,
            body=body,
            status="pending",
            created_at=now,
        )
        db.add(alarm)
        created.append(alarm)
    db.flush()
    return created


def deliver(db: Session, user: User, now: datetime, mailer: Mailer, app_url: str) -> Counter:
    """Sends the person's pending alarms that may go now; returns what happened to each."""
    counts: Counter = Counter()
    pending = list(
        db.scalars(
            select(Alarm)
            .where(Alarm.user_id == user.id, Alarm.status == "pending")
            .order_by(Alarm.severity.desc(), Alarm.created_at)
        )
    )
    if not pending:
        return counts
    prefs = store.notification_settings(db, user.id)
    local = now.astimezone(zone(store.timezone_of(user)))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    sent = suggestions_sent(db, user.id, midnight)
    for alarm in pending:
        if now - store.utc(alarm.created_at) > EXPIRE_AFTER:
            alarm.status = "expired"
        elif prefs.quiet_start and _quiet(local.time(), prefs.quiet_start, prefs.quiet_end):
            continue  # waits for the end of quiet hours
        elif sent >= prefs.max_per_day:
            alarm.status, alarm.reason = "suppressed", "daily_limit"
        else:
            db.add(
                Notification(
                    user_id=user.id,
                    kind="alarm",
                    title=alarm.title[:80],
                    body=alarm.body[:400],
                    link=link(alarm),
                    created_at=now,
                )
            )
            if prefs.email:
                try:
                    mailer.send(compose(alarm, user, app_url))
                except MailError as error:
                    logger.warning("An alarm email failed: %s", str(error)[:200])
            alarm.status, alarm.sent_at = "sent", now
            sent += 1
        counts[alarm.status] += 1
    db.flush()
    return counts


def compose(alarm: Alarm, user: User, app_url: str) -> Email:
    link_url = f"{app_url.rstrip('/')}{link(alarm)}"
    text_body = f"{alarm.body}\n\nSee the numbers in Patterns: {link_url}\n"
    page = (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;color:#1F1A16;'
        'max-width:480px;line-height:1.5">'
        f'<p style="font-size:17px;margin:0 0 8px"><strong>{html.escape(alarm.title)}</strong></p>'
        f'<p style="font-size:15px;margin:0 0 16px">{html.escape(alarm.body)}</p>'
        f'<p style="font-size:13px;color:#6F655C;margin:0">A pattern in your own data, not '
        f'medical advice. <a href="{html.escape(link_url)}" style="color:#6F655C">See the '
        "numbers</a> or change alerts in Reminders.</p></div>"
    )
    return Email(to=user.email, subject=alarm.title, text=text_body, html=page)


def run_all(sessions: Sessions, now: datetime, mailer: Mailer, app_url: str) -> Counter:
    """Checks and delivers for everyone connected to Google; one failing person stops no one."""
    counts: Counter = Counter()
    with sessions() as db:
        people = list(db.scalars(select(GoogleConnection.user_id)))
    for user_id in people:
        try:
            with sessions() as db:
                user = db.get(User, user_id)
                if user is None or user.status != "approved":
                    continue
                connection = db.get(GoogleConnection, user_id)
                frame = with_scores(load_daily(db, user_id, SOURCE))
                created = check(
                    db, user, now, frame, reconnect_needed=connection.status == "reconnect_needed"
                )
                counts["created"] += len(created)
                counts.update(deliver(db, user, now, mailer, app_url))
        except Exception:
            logger.exception("Checking alarms failed for one person")
            counts["errors"] += 1
    return counts
