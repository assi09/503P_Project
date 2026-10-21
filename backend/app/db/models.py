"""Database tables. Only what is settled lives here; later features add tables by migration.

Every table that holds a person's data has a `user_id`, and every query filters on it.
Types are portable so the tests can run on SQLite while development and deployment use Postgres.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Where a day's numbers came from. A history is read from one source only: the legacy export's
# sleep comes from an older algorithm than the API's, so mixing them would fake a change.
SOURCES = ("google_health", "takeout")
SYNC_STATUSES = ("running", "succeeded", "failed")


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GoogleConnection(Base):
    """A user's Google Health sign-in. The token is stored encrypted, never in plain text."""

    __tablename__ = "google_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # "active", or "reconnect_needed" once Google rejects the refresh token (7 days in Testing).
    status: Mapped[str] = mapped_column(String(32), default="active")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class DailyMetric(Base):
    """One metric on one local day, for one user and source (the columns in docs/metrics.md)."""

    __tablename__ = "daily_metrics"
    __table_args__ = (
        CheckConstraint(f"source IN {SOURCES}", name="ck_daily_metrics_source"),
        Index("ix_daily_metrics_user_metric_day", "user_id", "metric", "day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class SyncRun(Base):
    """One attempt to pull data, kept for the Data tab and for operational metrics."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(f"source IN {SOURCES}", name="ck_sync_runs_source"),
        CheckConstraint(f"status IN {SYNC_STATUSES}", name="ck_sync_runs_status"),
        Index("ix_sync_runs_user_started", "user_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="running")
    range_start: Mapped[date] = mapped_column(Date)
    range_end: Mapped[date] = mapped_column(Date)  # exclusive
    days_written: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)  # safe to show the user
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
