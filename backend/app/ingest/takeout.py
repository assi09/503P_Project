"""Build a daily metrics table from a Google Takeout Fitbit ("Google Health") export.

Only health metrics are read. Profile and account files (name, email, birth date) are never opened.

Intraday files are timestamped in UTC and are bucketed into days in the user's local timezone.
Daily files are keyed by calendar date (stored as midnight UTC), so their date is used as-is.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ACTIVITY_DIR = "Physical Activity_GoogleData"
LEGACY_DIR = "Global Export Data"  # Fitbit's own export format: sleep logs and daily totals


class IngestError(ValueError):
    """The export is missing, unreadable, or not in the expected format."""


MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class Metric:
    name: str
    folder: str
    column: str
    intraday: bool  # intraday values are summed per local day; daily values are taken as-is
    scale: float = 1.0  # unit conversion applied after aggregation


METRICS = (
    Metric("steps", "Steps", "steps", intraday=True),
    Metric("calories", "Calories", "calories", intraday=True),
    Metric("distance_km", "Distance", "distance", intraday=True, scale=0.001),  # meters in export
    # Fitbit counts cardio and peak minutes double; the export already stores them as 2.
    Metric("active_zone_minutes", "Active Zone Minutes", "total minutes", intraday=True),
    Metric("cardio_load", "Cardio Load", "total", intraday=True),
    Metric("resting_hr", "Daily Resting Heart Rate", "beats per minute", intraday=False),
    Metric(
        "hrv_ms",
        "Daily Heart Rate Variability",
        "average heart rate variability milliseconds",
        intraday=False,
    ),
    Metric("respiratory_rate", "Daily Respiratory Rate", "breaths per minute", intraday=False),
    Metric("readiness", "Daily Readiness", "score", intraday=False),
)

# Fitbit's own daily activity-minute totals. The per-minute `Activity Level` labels use a different
# classification and do not add up to these, so they are only used for wear time.
ACTIVITY_MINUTES = (
    "sedentary_minutes",
    "lightly_active_minutes",
    "moderately_active_minutes",
    "very_active_minutes",
)

SLEEP_STAGES = {
    "deep": "deep_sleep_minutes",
    "light": "light_sleep_minutes",
    "rem": "rem_sleep_minutes",
    "wake": "awake_in_bed_minutes",
}


@dataclass
class DailyData:
    frame: pd.DataFrame  # one row per local date, one column per metric
    missing: list[str] = field(default_factory=list)  # metrics absent from the export


def find_export_root(path: Path) -> Path:
    """Return the `Google Health` directory inside an extracted Takeout export."""
    path = Path(path)
    if path.name == "Google Health" and path.is_dir():
        return path
    for candidate in (path / "Google Health", path / "Takeout" / "Google Health"):
        if candidate.is_dir():
            return candidate
    raise IngestError(f"No 'Google Health' folder found under {path}")


def _read_csvs(folder: Path, required: set[str]) -> pd.DataFrame | None:
    files = sorted(folder.glob("*.csv"))
    if not files:
        return None
    frames = []
    for file in files:
        try:
            frame = pd.read_csv(file)
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise IngestError(f"Unreadable file {file.name}: {exc}") from exc
        missing = required - set(frame.columns)
        if missing:
            raise IngestError(f"{file.name} is missing columns {sorted(missing)}")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _local_dates(timestamps: pd.Series, tz: str) -> pd.Series:
    parsed = pd.to_datetime(timestamps, utc=True, errors="coerce", format="ISO8601")
    if parsed.isna().any():
        raise IngestError(f"{int(parsed.isna().sum())} unparseable timestamps")
    return parsed.dt.tz_convert(tz).dt.date


def _calendar_dates(timestamps: pd.Series) -> pd.Series:
    dates = pd.to_datetime(timestamps.astype(str).str[:10], errors="coerce", format="%Y-%m-%d")
    if dates.isna().any():
        raise IngestError(f"{int(dates.isna().sum())} unparseable dates")
    return dates.dt.date


def _read_metric(root: Path, metric: Metric, tz: str) -> pd.Series | None:
    frame = _read_csvs(root / ACTIVITY_DIR / metric.folder, {"timestamp", metric.column})
    if frame is None:
        return None
    values = pd.to_numeric(frame[metric.column], errors="coerce")
    if metric.intraday:
        daily = values.groupby(_local_dates(frame["timestamp"], tz)).sum(min_count=1)
    else:
        daily = values.groupby(_calendar_dates(frame["timestamp"])).mean()
    return daily * metric.scale


def _read_json_list(file: Path) -> list:
    try:
        return json.loads(file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IngestError(f"Unreadable file {file.name}: {exc}") from exc


def _read_activity_minutes(root: Path) -> pd.DataFrame | None:
    columns = {}
    for name in ACTIVITY_MINUTES:
        values = {}
        for file in sorted((root / LEGACY_DIR).glob(f"{name}-*.json")):
            for entry in _read_json_list(file):
                try:
                    day = pd.to_datetime(entry["dateTime"], format="%m/%d/%y %H:%M:%S").date()
                    values[day] = float(entry["value"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise IngestError(f"Malformed entry in {file.name}: {exc}") from exc
        if values:
            columns[name] = pd.Series(values)
    if not columns:
        return None
    frame = pd.DataFrame(columns).reindex(columns=list(ACTIVITY_MINUTES))
    # Fitbit reports a full day of sedentary time on days the device recorded nothing.
    frame[frame["sedentary_minutes"] >= MINUTES_PER_DAY] = float("nan")
    return frame.dropna(how="all")


def _read_wear_minutes(root: Path, tz: str) -> pd.DataFrame | None:
    frame = _read_csvs(root / ACTIVITY_DIR / "Activity Level", {"timestamp", "level"})
    if frame is None:
        return None
    # Activity level is only recorded for awake minutes with the device on: a wear-time signal.
    dates = _local_dates(frame["timestamp"], tz)
    return frame.groupby(dates).size().rename("wear_minutes").to_frame()


def _sleep_row(log: dict) -> dict:
    start = pd.Timestamp(log["startTime"])  # already local time, no offset
    # Bedtime as hours relative to midnight: 23:30 -> -0.5, 01:00 -> 1.0
    bedtime = start.hour + start.minute / 60
    if bedtime >= 12:
        bedtime -= 24
    row = {
        "sleep_minutes": log["minutesAsleep"],
        "time_in_bed": log["timeInBed"],
        "sleep_efficiency": log["efficiency"],
        "bedtime_hour": round(bedtime, 2),
    }
    # Only "stages" logs have deep/light/rem; "classic" logs (short or low-signal nights) do not.
    summary = log.get("levels", {}).get("summary", {}) if log["type"] == "stages" else {}
    for stage, column in SLEEP_STAGES.items():
        row[column] = summary.get(stage, {}).get("minutes")
    return row


def _read_sleep(root: Path) -> pd.DataFrame | None:
    files = sorted((root / LEGACY_DIR).glob("sleep-*.json"))
    if not files:
        return None
    logs = []
    for file in files:
        logs.extend(_read_json_list(file))

    # Keep the longest main sleep per night; naps are ignored.
    best: dict[str, dict] = {}
    for log in logs:
        try:
            if not log["mainSleep"]:
                continue
            date = log["dateOfSleep"]
            if date not in best or log["minutesAsleep"] > best[date]["minutesAsleep"]:
                best[date] = log
        except (KeyError, TypeError) as exc:
            raise IngestError(f"Malformed sleep log: {exc}") from exc

    if not best:
        return None
    rows = {pd.Timestamp(date).date(): _sleep_row(log) for date, log in best.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def load_daily(path: Path, tz: str) -> DailyData:
    """Load an extracted Takeout export into a daily metrics table."""
    root = find_export_root(path)
    columns: list[pd.Series | pd.DataFrame] = []
    missing: list[str] = []

    for metric in METRICS:
        series = _read_metric(root, metric, tz)
        if series is None:
            missing.append(metric.name)
        else:
            columns.append(series.rename(metric.name))

    grouped_readers = (
        ("activity_minutes", lambda: _read_activity_minutes(root)),
        ("wear_minutes", lambda: _read_wear_minutes(root, tz)),
        ("sleep", lambda: _read_sleep(root)),
    )
    for name, read in grouped_readers:
        frame = read()
        if frame is None:
            missing.append(name)
        else:
            columns.append(frame)

    if not columns:
        raise IngestError("Export contains none of the supported metrics")
    if missing:
        logger.warning("Metrics missing from export: %s", ", ".join(missing))

    frame = pd.concat(columns, axis=1).sort_index()
    frame.index = pd.DatetimeIndex(frame.index, name="date")
    full_range = pd.date_range(frame.index.min(), frame.index.max(), freq="D", name="date")
    return DailyData(frame=frame.reindex(full_range), missing=missing)
