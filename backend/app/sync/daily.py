"""Build the daily metrics table from the Google Health API.

Produces the same columns as the Takeout ingestion (docs/metrics.md), so the analysis does not
care where the data came from. Days are the device's local calendar days: roll-ups and daily
types are keyed by civil date, and sleep by the local date it ended.

Sleep comes from Google's current sleep algorithm, which differs from the legacy Fitbit export by
tens of minutes a night; a history must come from one source, never a mix of both.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

import pandas as pd

from app.ingest.takeout import DailyData
from app.sync.client import HealthClient

logger = logging.getLogger(__name__)

# Columns the Takeout export has but the API does not provide. The API's sedentary periods are
# bouts of sitting, not Fitbit's daily sedentary total, so they are not passed off as one.
NOT_IN_API = ("cardio_load", "readiness", "sleep_score", "sedentary_minutes")

ACTIVE_MINUTES = {
    "LIGHT": "lightly_active_minutes",
    "MODERATE": "moderately_active_minutes",
    "VIGOROUS": "very_active_minutes",
}

SLEEP_STAGES = {
    "DEEP": "deep_sleep_minutes",
    "LIGHT": "light_sleep_minutes",
    "REM": "rem_sleep_minutes",
    "AWAKE": "awake_in_bed_minutes",
}


def _number(value) -> float | None:
    """The API sends 64-bit integers as strings."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _seconds(value: str | None) -> float | None:
    """Durations and UTC offsets come as strings like "10800s"."""
    return _number(value[:-1]) if isinstance(value, str) and value.endswith("s") else None


def _civil(value: dict) -> date:
    d = value.get("date", value)
    return date(int(d["year"]), int(d["month"]), int(d["day"]))


def _local(time: str, offset: str | None) -> datetime:
    """A UTC timestamp moved to the device's local time, as a naive datetime."""
    utc = pd.Timestamp(time).tz_convert("UTC").tz_localize(None)
    return (utc + timedelta(seconds=_seconds(offset) or 0)).to_pydatetime()


def _zone_minutes(value: dict) -> float | None:
    # The cardio and peak sums already count each minute double, as Fitbit does.
    parts = [
        _number(value.get(key))
        for key in ("sumInFatBurnHeartZone", "sumInCardioHeartZone", "sumInPeakHeartZone")
    ]
    if all(part is None for part in parts):
        return None
    return sum(part or 0 for part in parts)


# Column -> (data type, value field in a roll-up point, how to read the value).
ROLLUPS: dict[str, tuple[str, str, Callable[[dict], float | None]]] = {
    "steps": ("steps", "steps", lambda v: _number(v.get("countSum"))),
    "distance_km": (
        "distance",
        "distance",
        lambda v: None if (mm := _number(v.get("millimetersSum"))) is None else mm / 1e6,
    ),
    "calories": ("total-calories", "totalCalories", lambda v: _number(v.get("kcalSum"))),
    "active_zone_minutes": ("active-zone-minutes", "activeZoneMinutes", _zone_minutes),
}

# Column -> (daily data type, field holding the value).
DAILY_VALUES = {
    "resting_hr": ("daily-resting-heart-rate", "beatsPerMinute"),
    "hrv_ms": ("daily-heart-rate-variability", "averageHeartRateVariabilityMilliseconds"),
    "respiratory_rate": ("daily-respiratory-rate", "breathsPerMinute"),
}


def _value_key(data_type: str) -> str:
    """`daily-resting-heart-rate` -> `dailyRestingHeartRate`, the field holding a point's data."""
    first, *rest = data_type.split("-")
    return first + "".join(word.capitalize() for word in rest)


def _date_filter(data_type: str, start: date, end: date) -> str:
    field = data_type.replace("-", "_")
    return f'{field}.date >= "{start.isoformat()}" AND {field}.date < "{end.isoformat()}"'


def _rollup_column(health: HealthClient, column: str, start: date, end: date) -> pd.Series:
    data_type, field, read = ROLLUPS[column]
    values = {
        _civil(point["civilStartTime"]): read(point[field])
        for point in health.daily_rollup(data_type, start, end)
        if field in point  # absent: no data that day
    }
    return pd.Series(values, name=column, dtype=float)


def _active_minutes(health: HealthClient, start: date, end: date) -> pd.DataFrame:
    rows: dict[date, dict[str, float]] = {}
    for point in health.daily_rollup("active-minutes", start, end):
        if "activeMinutes" not in point:
            continue
        row = dict.fromkeys(ACTIVE_MINUTES.values(), 0.0)  # a level with no minutes is left out
        for level in point["activeMinutes"].get("activeMinutesRollupByActivityLevel", []):
            column = ACTIVE_MINUTES.get(level.get("activityLevel"))
            if column:
                row[column] = _number(level.get("activeMinutesSum")) or 0.0
            else:
                logger.warning("Unknown activity level %r", level.get("activityLevel"))
        rows[_civil(point["civilStartTime"])] = row
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(ACTIVE_MINUTES.values()))


def _daily_value(health: HealthClient, column: str, start: date, end: date) -> pd.Series:
    data_type, field = DAILY_VALUES[column]
    key = _value_key(data_type)
    values = {
        _civil(point[key]["date"]): _number(point[key].get(field))
        for point in health.list_points(data_type, filter=_date_filter(data_type, start, end))
    }
    return pd.Series(values, name=column, dtype=float)


def _skin_temperature(health: HealthClient, start: date, end: date) -> pd.Series:
    data_type = "daily-sleep-temperature-derivations"
    key = _value_key(data_type)
    values = {}
    for point in health.list_points(data_type, filter=_date_filter(data_type, start, end)):
        value = point[key]
        nightly = _number(value.get("nightlyTemperatureCelsius"))
        baseline = _number(value.get("baselineTemperatureCelsius"))
        # The Fitbit app shows the night relative to the user's baseline; none until one exists.
        if nightly is not None and baseline is not None:
            values[_civil(value["date"])] = round(nightly - baseline, 3)
    return pd.Series(values, name="skin_temp_variation_c", dtype=float)


def _utc_filter(field: str, start: date, end: date) -> str:
    # Local days can start up to 14 hours either side of UTC midnight: widen by a day each side
    # and keep only the local dates asked for.
    low, high = start - timedelta(days=1), end + timedelta(days=1)
    return f'{field} >= "{low.isoformat()}T00:00:00Z" AND {field} < "{high.isoformat()}T00:00:00Z"'


def _wear_minutes(health: HealthClient, start: date, end: date) -> pd.Series:
    # Activity level is only recorded for awake minutes with the device on: a wear-time signal.
    minutes: dict[date, float] = {}
    query = _utc_filter("activity_level.interval.start_time", start, end)
    for point in health.list_points("activity-level", filter=query, page_size=10_000):
        interval = point["activityLevel"]["interval"]
        day = _civil(interval["civilStartTime"])
        length = pd.Timestamp(interval["endTime"]) - pd.Timestamp(interval["startTime"])
        minutes[day] = minutes.get(day, 0.0) + length.total_seconds() / 60
    series = pd.Series(minutes, name="wear_minutes", dtype=float)
    return series[(series.index >= start) & (series.index < end)]


def _sleep_row(sleep: dict) -> dict:
    interval, summary = sleep["interval"], sleep["summary"]
    begin = _local(interval["startTime"], interval.get("startUtcOffset"))
    finish = _local(interval["endTime"], interval.get("endUtcOffset"))
    in_bed = (finish - begin).total_seconds() / 60
    asleep = _number(summary.get("minutesAsleep"))
    # Bedtime as hours relative to midnight: 23:30 -> -0.5, 01:00 -> 1.0
    bedtime = begin.hour + begin.minute / 60
    if bedtime >= 12:
        bedtime -= 24
    row = {
        "sleep_minutes": asleep,
        "time_in_bed": round(in_bed),
        # Our definition (the API has no efficiency): share of the time in bed spent asleep.
        "sleep_efficiency": round(100 * asleep / in_bed) if asleep and in_bed > 0 else None,
        "bedtime_hour": round(bedtime, 2),
    }
    stages = {s.get("type"): _number(s.get("minutes")) for s in summary.get("stagesSummary", [])}
    staged = sleep.get("type") == "STAGES"  # "CLASSIC" nights only know asleep and awake
    for stage, column in SLEEP_STAGES.items():
        row[column] = stages.get(stage) if staged else None
    return row


def _sleep(health: HealthClient, start: date, end: date) -> pd.DataFrame:
    # Keep the longest main sleep per night, dated by the local day it ended; naps are ignored.
    best: dict[date, dict] = {}
    query = _utc_filter("sleep.interval.end_time", start, end)
    for point in health.list_points("sleep", filter=query, page_size=25):
        sleep = point["sleep"]
        if not sleep.get("metadata", {}).get("mainSleep"):
            continue
        interval = sleep["interval"]
        night = _local(interval["endTime"], interval.get("endUtcOffset")).date()
        if not start <= night < end:
            continue
        asleep = _number(sleep["summary"].get("minutesAsleep")) or 0
        current = best.get(night)
        if current is None or asleep > (_number(current["summary"].get("minutesAsleep")) or 0):
            best[night] = sleep
    rows = {night: _sleep_row(sleep) for night, sleep in best.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def load_daily(health: HealthClient, start: date, end: date) -> DailyData:
    """The daily table for local days in [start, end), read from the Google Health API."""
    columns: list[pd.Series | pd.DataFrame] = [
        *(_rollup_column(health, column, start, end) for column in ROLLUPS),
        _active_minutes(health, start, end),
        _wear_minutes(health, start, end),
        *(_daily_value(health, column, start, end) for column in DAILY_VALUES),
        _skin_temperature(health, start, end),
        _sleep(health, start, end),
    ]
    frame = pd.concat(columns, axis=1)
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index), name="date")
    full_range = pd.date_range(start, end - timedelta(days=1), freq="D", name="date")
    frame = frame.reindex(full_range)
    empty = [column for column in frame.columns if frame[column].isna().all()]
    return DailyData(frame=frame, missing=[*NOT_IN_API, *empty])
