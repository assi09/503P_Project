"""Loads each person's daily metrics and the analysis the API serves.

A person's data is their live Google Health days from the database. Only the owner (an admin)
falls back to the Takeout export at `settings.export_dir`, and only when they have no live data
at all: a history comes from one source, never a mix (the two use different sleep algorithms).
Analyses are cached per person until their data changes.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evidence import Evidence
from app.analysis.report import Report, build_report
from app.analysis.screen import screen
from app.api.auth import Db, approved_user, is_admin
from app.auth.accounts import AuthError
from app.config import settings
from app.db.daily import load_daily as load_stored
from app.db.models import DailyMetric, SyncRun, User
from app.ingest.takeout import DailyData, IngestError
from app.ingest.takeout import load_daily as load_takeout

Source = Literal["google_health", "takeout"]


@dataclass(frozen=True)
class LoadedData:
    daily: DailyData
    loaded_at: datetime  # when the data was last updated: the last sync, or the export's load
    report: Report
    evidence: dict[str, Evidence]  # everything computed, by id, so any citation resolves
    source: Source = "takeout"


def analyze(daily: DailyData, loaded_at: datetime, source: Source = "takeout") -> LoadedData:
    result = screen(daily.frame)
    report = build_report(daily.frame, result, created_at=loaded_at)
    evidence = {e.id: e for e in result.tested}
    return LoadedData(daily, loaded_at, report, evidence, source)


@lru_cache(maxsize=1)
def _load() -> LoadedData:
    """The owner's Takeout export, read once."""
    daily = load_takeout(settings.export_dir, settings.timezone)
    return analyze(daily, datetime.now(UTC))


# Live analyses by user id, each with the version of the data it was computed from.
_live: dict[object, tuple[tuple, LoadedData]] = {}


def _live_version(db: Session, user: User) -> tuple | None:
    """Changes whenever the person's stored live data does; None when they have none."""
    days, last_day = db.execute(
        select(func.count(DailyMetric.value), func.max(DailyMetric.day)).where(
            DailyMetric.user_id == user.id, DailyMetric.source == "google_health"
        )
    ).one()
    if not days:
        return None
    synced = db.scalar(
        select(func.max(SyncRun.finished_at)).where(
            SyncRun.user_id == user.id,
            SyncRun.source == "google_health",
            SyncRun.status == "succeeded",
        )
    )
    return (days, last_day, synced)


def load_for(db: Session, user: User, now: datetime) -> LoadedData:
    version = _live_version(db, user)
    if version is not None:
        cached = _live.get(user.id)
        if cached and cached[0] == version:
            return cached[1]
        frame = load_stored(db, user.id, "google_health")
        synced = version[2]
        if synced is not None and synced.tzinfo is None:  # SQLite drops the zone
            synced = synced.replace(tzinfo=UTC)
        loaded = analyze(DailyData(frame=frame), synced or now, "google_health")
        _live[user.id] = (version, loaded)
        return loaded
    if is_admin(user):
        try:
            return _load()
        except IngestError:
            pass  # no export on this server either
    raise AuthError(404, "no_data", "Your Fitbit data is not connected yet.")


def get_data(user: Annotated[User, Depends(approved_user)], db: Db) -> LoadedData:
    """FastAPI dependency: the signed-in person's own data. Tests may override it."""
    return load_for(db, user, datetime.now(UTC))
