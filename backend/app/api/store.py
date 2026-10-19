"""Loads the user's daily metrics and the analysis the API serves.

Single-user for now: the daily table comes from the Takeout export at `settings.export_dir` and is
analyzed once, then cached. Per-user storage replaces this once accounts exist.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from app.analysis.evidence import Evidence
from app.analysis.report import Report, build_report
from app.analysis.screen import screen
from app.config import settings
from app.ingest.takeout import DailyData, load_daily


@dataclass(frozen=True)
class LoadedData:
    daily: DailyData
    loaded_at: datetime
    report: Report
    evidence: dict[str, Evidence]  # everything computed, by id, so any citation resolves


def analyze(daily: DailyData, loaded_at: datetime) -> LoadedData:
    result = screen(daily.frame)
    report = build_report(daily.frame, result, created_at=loaded_at)
    evidence = {e.id: e for e in result.tested}
    return LoadedData(daily=daily, loaded_at=loaded_at, report=report, evidence=evidence)


@lru_cache(maxsize=1)
def _load() -> LoadedData:
    daily = load_daily(settings.export_dir, settings.timezone)
    return analyze(daily, datetime.now(UTC))


def get_data() -> LoadedData:
    """FastAPI dependency; tests override it with synthetic data."""
    return _load()
