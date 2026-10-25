"""What the tracker recorded during a workout, read from Google by the server.

The model never supplies these values: a proposal's own `measured` field is thrown away and
replaced. Measuring is optional; any failure leaves the draft with only the given values.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.actions.schemas import Measured, Overlap, WorkoutLog
from app.sync.client import HealthClient
from app.sync.google_auth import SyncError

logger = logging.getLogger(__name__)

Measurer = Callable[[datetime, datetime], Measured]
# An exercise overlapping the workout starts at most this long before it (the longest workout).
LOOKBACK = timedelta(hours=24)


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
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


def measure(health: HealthClient, start: datetime, end: datetime) -> Measured:
    try:
        overlaps = _overlaps(health, start, end)
        heart = health.rollup("heart-rate", start, end).get("heartRate", {})
        average = _number(heart.get("beatsPerMinuteAvg"))
        if not average:
            # No heart rate means the tracker was not worn (or has not synced yet). Total
            # calories exist even then, estimated from resting burn, so none are sent.
            return Measured(status="no_data", overlaps=overlaps)
        steps = _number(health.rollup("steps", start, end).get("steps", {}).get("countSum"))
        millimetres = _number(
            health.rollup("distance", start, end).get("distance", {}).get("millimetersSum")
        )
        calories = _number(
            health.rollup("total-calories", start, end).get("totalCalories", {}).get("kcalSum")
        )
    except (SyncError, ValueError, AttributeError):
        logger.warning("Could not read the tracker's data for a workout")  # no values logged
        return Measured(status="unavailable")
    return Measured(
        status="measured",
        steps=round(steps) if steps is not None else None,
        distance_km=round(millimetres / 1_000_000, 3) if millimetres else None,
        # Total, not active, calories: what Fitbit shows for an exercise (checked on 8 workouts).
        calories_kcal=round(calories) if calories is not None else None,
        average_heart_rate=round(average),
        overlaps=overlaps,
    )


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
        measurer(log.start_time, log.end_time) if measurer else Measured(status="unavailable")
    )
    return payload | {
        "measured": measured.model_dump(mode="json", by_alias=True, exclude_none=True)
    }
