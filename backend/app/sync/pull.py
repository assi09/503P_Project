"""Pulling a user's days from the Google Health API into the database, as a recorded sync run."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.daily import save_daily
from app.db.models import SyncRun, User
from app.sync.client import HealthClient
from app.sync.daily import load_daily
from app.sync.google_auth import SyncError

SOURCE = "google_health"

Sessions = Callable[[], AbstractContextManager[Session]]


def get_or_create_user(session: Session, email: str) -> User:
    email = email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        # Whoever runs the sync on this machine owns the data, so there is nothing to approve.
        user = User(email=email, status="approved")
        session.add(user)
        session.flush()
    return user


def pull(sessions: Sessions, health: HealthClient, email: str, start: date, end: date) -> SyncRun:
    """Fetches local days [start, end) and stores them. The run is recorded even if it fails."""
    with sessions() as session:
        user = get_or_create_user(session, email)
        run = SyncRun(user_id=user.id, source=SOURCE, range_start=start, range_end=end)
        session.add(run)

    try:
        daily = load_daily(health, start, end)
        with sessions() as session:
            written = save_daily(session, run.user_id, SOURCE, daily.frame)
    except SyncError as exc:
        _finish(sessions, run, "failed", error=str(exc))
        raise
    _finish(sessions, run, "succeeded", days_written=written)
    return run


def _finish(sessions: Sessions, run: SyncRun, status: str, **fields) -> None:
    with sessions() as session:
        stored = session.get(SyncRun, run.id)
        stored.status = status
        stored.finished_at = datetime.now(UTC)
        for name, value in fields.items():
            setattr(stored, name, value)
    run.status = status
    for name, value in fields.items():
        setattr(run, name, value)
