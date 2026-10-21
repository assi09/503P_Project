"""Storing and reading a user's daily table (one row per user, source, day and metric)."""

import uuid
from datetime import date

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import SOURCES, DailyMetric


def save_daily(session: Session, user_id: uuid.UUID, source: str, frame: pd.DataFrame) -> int:
    """Replaces the stored values of every day in `frame`; returns the number of days written.

    Each day in the frame is rewritten as a whole, so a metric that is now missing on a day (for
    example sleep rescored away) does not survive from an earlier sync.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}")
    days = [day.date() for day in pd.DatetimeIndex(frame.index)]
    if not days:
        return 0
    session.execute(
        delete(DailyMetric).where(
            DailyMetric.user_id == user_id,
            DailyMetric.source == source,
            DailyMetric.day.in_(days),
        )
    )
    long = frame.stack().dropna()  # (day, metric) -> value, without empty cells
    session.add_all(
        DailyMetric(user_id=user_id, source=source, day=day.date(), metric=metric, value=float(v))
        for (day, metric), v in long.items()
    )
    return len(days)


def load_daily(
    session: Session,
    user_id: uuid.UUID,
    source: str,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """The stored daily table for [start, end), one row per day with every stored metric."""
    query = select(DailyMetric.day, DailyMetric.metric, DailyMetric.value).where(
        DailyMetric.user_id == user_id, DailyMetric.source == source
    )
    if start:
        query = query.where(DailyMetric.day >= start)
    if end:
        query = query.where(DailyMetric.day < end)
    rows = session.execute(query).all()
    if not rows:
        return pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
    long = pd.DataFrame(rows, columns=["day", "metric", "value"])
    frame = long.pivot(index="day", columns="metric", values="value")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index), name="date")
    frame.columns.name = None
    return frame.sort_index()
