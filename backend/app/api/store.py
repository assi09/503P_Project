"""Loads the user's daily metrics for the API.

Single-user for now: the daily table comes from the Takeout export at `settings.export_dir` and is
cached after the first load. Per-user storage replaces this once accounts exist.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from app.config import settings
from app.ingest.takeout import DailyData, load_daily


@dataclass(frozen=True)
class LoadedData:
    daily: DailyData
    loaded_at: datetime


@lru_cache(maxsize=1)
def _load() -> LoadedData:
    daily = load_daily(settings.export_dir, settings.timezone)
    return LoadedData(daily=daily, loaded_at=datetime.now(UTC))


def get_data() -> LoadedData:
    """FastAPI dependency; tests override it with synthetic data."""
    return _load()
