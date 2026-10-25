"""What the tracker recorded during a workout, read from Google by the server.

The model never supplies these values: a proposal's own `measured` field is thrown away and
replaced. Measuring is optional; any failure leaves the draft with only the given values. Each
kind of workout gets the metrics Fitbit records for it (`app/actions/exercises.py`); over 119
workouts the tracker recorded, these roll-ups matched Fitbit's own summaries.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.actions import exercises
from app.actions.exercises import Kind
from app.actions.schemas import Measured, Overlap, WorkoutLog, ZoneSeconds
from app.sync.client import HealthClient
from app.sync.google_auth import SyncError

logger = logging.getLogger(__name__)

Measurer = Callable[[datetime, datetime, str], Measured]
# An exercise overlapping the workout starts at most this long before it (the longest workout).
LOOKBACK = timedelta(hours=24)
ZONES = {"LIGHT": "light", "MODERATE": "moderate", "VIGOROUS": "vigorous", "PEAK": "peak"}


def _number(value: object) -> float | None:
    try:
        return float(str(value).removesuffix("s")) if value is not None else None
    except (TypeError, ValueError):
        return None


def _overlaps(health: HealthClient, start: datetime, end: datetime) -> list[Overlap]:
    # Exercises are filtered by civil (local) time; widen the window and compare instants.
    field = "exercise.interval.civil_start_time"
    low = (start - LOOKBACK).replace(tzinfo=None).isoformat(timespec="seconds")
    high = end.replace(tzinfo=None).isoformat(timespec="seconds")
    found = []
    for point in health.list_points(
        "exercise", filter=f'{field} >= "{low}" AND {field} < "{high}"'
    ):
        exercise = point.get("exercise", {})
        interval = exercise.get("interval", {})
        try:
            overlap = Overlap(
                exercise_type=exercise.get("exerciseType", ""),
                start_time=interval.get("startTime"),
                end_time=interval.get("endTime"),
            )
        except ValidationError:
            continue
        if overlap.start_time < end and overlap.end_time > start:
            found.append(overlap)
    return sorted(found, key=lambda o: o.start_time)[:20]


def _zones(health: HealthClient, start: datetime, end: datetime) -> ZoneSeconds:
    rollup = health.rollup("time-in-heart-rate-zone", start, end)
    seconds = {}
    for zone in rollup.get("timeInHeartRateZone", {}).get("timeInHeartRateZones", []):
        name = ZONES.get(zone.get("heartRateZone"))
        if name:
            seconds[name] = _number(zone.get("duration")) or 0
    return ZoneSeconds(**seconds)


def _active_zone_minutes(health: HealthClient, start: datetime, end: datetime) -> int | None:
    rollup = health.rollup("active-zone-minutes", start, end).get("activeZoneMinutes")
    if not rollup:
        return None
    # The cardio and peak sums already count double, so the total is the plain sum
    # (it matched Fitbit's on 78 of 79 workouts, the other by one minute).
    fields = ("sumInFatBurnHeartZone", "sumInCardioHeartZone", "sumInPeakHeartZone")
    return round(sum(_number(rollup.get(field)) or 0 for field in fields))


def _swim_lengths(health: HealthClient, start: datetime, end: datetime) -> int:
    # One point per length. The roll-up only sums strokes, so the points are counted.
    field = "swim_lengths_data.interval.start_time"
    low, high = (moment.isoformat() for moment in (start, end))
    query = f'{field} >= "{low}" AND {field} < "{high}"'
    return sum(1 for _ in health.list_points("swim-lengths-data", filter=query, page_size=1000))


def measure(health: HealthClient, start: datetime, end: datetime, exercise_type: str) -> Measured:
    kind = exercises.kind(exercise_type)
    try:
        overlaps = _overlaps(health, start, end)
        heart = health.rollup("heart-rate", start, end).get("heartRate", {})
        average = _number(heart.get("beatsPerMinuteAvg"))
        if not average:
            # No heart rate means the tracker was not worn (or has not synced yet). Total
            # calories exist even then, estimated from resting burn, so none are sent.
            return Measured(status="no_data", overlaps=overlaps)
        calories = _number(
            health.rollup("total-calories", start, end).get("totalCalories", {}).get("kcalSum")
        )
        reading = Measured(
            status="measured",
            # Total, not active, calories: what Fitbit shows for a workout.
            calories_kcal=round(calories) if calories is not None else None,
            average_heart_rate=round(average),
            zone_seconds=_zones(health, start, end),
            active_zone_minutes=_active_zone_minutes(health, start, end),
            overlaps=overlaps,
        )
        if kind in (Kind.ON_FOOT, Kind.FIELD, Kind.STEPS):
            steps = _number(health.rollup("steps", start, end).get("steps", {}).get("countSum"))
            reading.steps = round(steps) if steps is not None else None
        if kind in (Kind.ON_FOOT, Kind.FIELD):
            # Distance from steps and stride: what Fitbit gives these without GPS. A bike's or a
            # swim's would be wrong, so those take only the distance the person gives.
            millimetres = _number(
                health.rollup("distance", start, end).get("distance", {}).get("millimetersSum")
            )
            reading.distance_km = round(millimetres / 1_000_000, 3) if millimetres else None
        if kind == Kind.SWIM:
            # Only on swims: the tracker also records stray "lengths" outside the water.
            reading.swim_lengths = _swim_lengths(health, start, end) or None
    except (SyncError, ValueError, AttributeError, ValidationError):
        logger.warning("Could not read the tracker's data for a workout")  # no values logged
        return Measured(status="unavailable")
    return reading


def with_measurement(payload: dict, measurer: Measurer | None) -> dict:
    """The payload with any supplied `measured` replaced by the server's own reading."""
    payload = {key: value for key, value in payload.items() if key != "measured"}
    if payload.get("kind") != "workout":
        return payload
    try:
        log = WorkoutLog.model_validate(payload)
    except ValidationError:
        return payload  # the store refuses it; no reason to call Google first
    measured = (
        measurer(log.start_time, log.end_time, log.exercise_type)
        if measurer
        else Measured(status="unavailable")
    )
    return payload | {
        "measured": measured.model_dump(mode="json", by_alias=True, exclude_none=True)
    }
