import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.actions import exercises
from app.actions.exercises import Kind
from app.actions.measure import measure, with_measurement
from app.actions.schemas import LOG, Measured, ZoneSeconds
from app.actions.tools import proposal_tools
from app.db.models import User
from app.sync.client import HealthClient

START = datetime.fromisoformat("2026-10-24T08:00:00+03:00")
END = datetime.fromisoformat("2026-10-24T08:30:00+03:00")
WORKOUT = {
    "kind": "workout",
    "exerciseType": "WALKING",
    "startTime": START.isoformat(),
    "endTime": END.isoformat(),
    "activeSeconds": 1500,
}
ZONES = ZoneSeconds(light=600, moderate=300, vigorous=60, peak=0)
READING = Measured(
    status="measured",
    steps=2400,
    distance_km=1.8,
    calories_kcal=120,
    average_heart_rate=101,
    zone_seconds=ZONES,
    active_zone_minutes=12,
)
ROLLUPS = {
    "heart-rate": {"heartRate": {"beatsPerMinuteAvg": 100.6, "beatsPerMinuteMax": 120}},
    "steps": {"steps": {"countSum": "2400"}},
    "distance": {"distance": {"millimetersSum": "1800000"}},
    "total-calories": {"totalCalories": {"kcalSum": 119.6}},
    "time-in-heart-rate-zone": {
        "timeInHeartRateZone": {
            "timeInHeartRateZones": [
                {"heartRateZone": "LIGHT", "duration": "600s"},
                {"heartRateZone": "MODERATE", "duration": "300s"},
                {"heartRateZone": "VIGOROUS", "duration": "60s"},
                {"heartRateZone": "UNKNOWN_ZONE", "duration": "99s"},
            ]
        }
    },
    # Cardio and peak are already doubled by Google: the total is the plain sum.
    "active-zone-minutes": {
        "activeZoneMinutes": {
            "sumInFatBurnHeartZone": "6",
            "sumInCardioHeartZone": "6",
            "sumInPeakHeartZone": "0",
        }
    },
}


def exercise(kind, start, end):
    return {"exercise": {"exerciseType": kind, "interval": {"startTime": start, "endTime": end}}}


class FakeGoogle:
    """Answers roll-ups and lists by data type and records what was asked."""

    def __init__(self, rollups=None, exercises=(), lengths=0, status=200):
        self.rollups = ROLLUPS if rollups is None else rollups
        self.exercises = list(exercises)
        self.lengths = lengths
        self.status = status
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx2.Response(self.status, json={"error": {"message": "boom"}})
        data_type = request.url.path.split("/dataTypes/")[1].split("/")[0]
        if request.url.path.endswith(":rollUp"):
            point = self.rollups.get(data_type)
            return httpx2.Response(200, json={"rollupDataPoints": [point] if point else []})
        if data_type == "swim-lengths-data":
            return httpx2.Response(200, json={"dataPoints": [{}] * self.lengths})
        return httpx2.Response(200, json={"dataPoints": self.exercises})

    def client(self) -> HealthClient:
        http = httpx2.Client(transport=httpx2.MockTransport(self))
        return HealthClient(lambda: "token", http=http, max_retries=0)

    def asked(self, data_type: str) -> bool:
        return any(f"/dataTypes/{data_type}/" in r.url.path for r in self.requests)


def test_every_google_type_is_accepted_and_named():
    assert len(exercises.TYPES) == len(set(exercises.TYPES)) > 180
    for group in (exercises.ON_FOOT, exercises.FIELD, exercises.STEPS, exercises.SWIM):
        assert group <= set(exercises.TYPES)
    for exercise_type in exercises.TYPES:
        log = LOG.validate_python(WORKOUT | {"exerciseType": exercise_type})
        assert log.google_payload()["exercise"]["displayName"]
    assert exercises.name("TENNIS") == "Tennis"
    assert exercises.name("KICKBOXING") == "Kickboxing"
    assert exercises.name("PICKELBALL") == "Pickleball"
    with pytest.raises(ValidationError):
        LOG.validate_python(WORKOUT | {"exerciseType": "EXERCISE_TYPE_UNSPECIFIED"})


def test_a_walk_is_measured_like_fitbit_does():
    google = FakeGoogle()
    measured = measure(google.client(), START, END, "WALKING")
    assert measured == READING
    rollup = next(r for r in google.requests if r.url.path.endswith("heart-rate/dataPoints:rollUp"))
    assert json.loads(rollup.content)["range"] == {
        "startTime": "2026-10-24T05:00:00Z",
        "endTime": "2026-10-24T05:30:00Z",
    }
    listing = next(r for r in google.requests if r.method == "GET")
    assert listing.url.params["filter"] == (
        'exercise.interval.civil_start_time >= "2026-10-23T08:00:00" AND '
        'exercise.interval.civil_start_time < "2026-10-24T08:30:00"'
    )
    assert not google.asked("swim-lengths-data")


@pytest.mark.parametrize(
    ("exercise_type", "steps", "distance"),
    [
        ("TENNIS", True, True),  # court and field sports: steps and distance, as Fitbit
        ("KICKBOXING", False, False),
        ("WEIGHTLIFTING", False, False),
        ("YOGA", False, False),
        ("BIKING", False, False),  # a distance from steps would be wrong on a bike
        ("ELLIPTICAL", True, False),
        ("ZUMBA", True, False),
    ],
)
def test_each_kind_gets_the_metrics_fitbit_records_for_it(exercise_type, steps, distance):
    google = FakeGoogle()
    measured = measure(google.client(), START, END, exercise_type)
    assert measured.calories_kcal == 120 and measured.average_heart_rate == 101
    assert measured.zone_seconds == ZONES and measured.active_zone_minutes == 12
    assert (measured.steps is not None) == steps == google.asked("steps")
    assert (measured.distance_km is not None) == distance == google.asked("distance")


def test_swim_lengths_are_counted_only_on_swims():
    google = FakeGoogle(lengths=24)
    swim = measure(google.client(), START, END, "SWIMMING_POOL")
    assert swim.swim_lengths == 24 and swim.steps is None and swim.distance_km is None
    listing = next(r for r in google.requests if "swim-lengths-data" in r.url.path)
    assert listing.url.params["filter"] == (
        'swim_lengths_data.interval.start_time >= "2026-10-24T08:00:00+03:00" AND '
        'swim_lengths_data.interval.start_time < "2026-10-24T08:30:00+03:00"'
    )
    other = FakeGoogle(lengths=24)
    assert measure(other.client(), START, END, "ROWING").swim_lengths is None
    assert not other.asked("swim-lengths-data")


def test_no_active_zone_minutes_is_left_out():
    rollups = {k: v for k, v in ROLLUPS.items() if k != "active-zone-minutes"}
    measured = measure(FakeGoogle(rollups=rollups).client(), START, END, "YOGA")
    assert measured.active_zone_minutes is None


def test_no_heart_rate_means_no_tracker_data_and_no_resting_calories():
    google = FakeGoogle(rollups={"total-calories": ROLLUPS["total-calories"]})
    assert measure(google.client(), START, END, "TENNIS") == Measured(status="no_data")
    assert not google.asked("total-calories")


@pytest.mark.parametrize("status", [401, 403, 500])
def test_google_failures_leave_the_draft_unmeasured(status):
    measured = measure(FakeGoogle(status=status).client(), START, END, "WALKING")
    assert measured == Measured(status="unavailable")


def test_only_exercises_overlapping_the_interval_are_reported():
    google = FakeGoogle(
        exercises=[
            exercise("WALKING", "2026-10-24T05:20:00Z", "2026-10-24T05:40:00Z"),  # overlaps
            exercise("RUNNING", "2026-10-24T04:00:00Z", "2026-10-24T05:00:00Z"),  # ends at start
            exercise("BIKING", "2026-10-24T05:30:00Z", "2026-10-24T06:00:00Z"),  # starts at end
            exercise("<script>", "2026-10-24T05:10:00Z", "2026-10-24T05:20:00Z"),  # malformed
            {"exercise": {"exerciseType": "YOGA"}},  # no interval
        ]
    )
    overlaps = measure(google.client(), START, END, "WALKING").overlaps
    assert [o.exercise_type for o in overlaps] == ["WALKING"]


def summary(log: dict) -> dict:
    return LOG.validate_python(log).google_payload()["exercise"]["metricsSummary"]


def test_the_persons_values_win_and_the_tracker_fills_in_the_rest():
    reading = READING.model_dump(by_alias=True)
    assert summary(WORKOUT | {"distanceKm": 2.0, "measured": reading}) == {
        "distanceMillimeters": 2_000_000,  # what the person said, not the measured 1.8 km
        "averagePaceSecondsPerMeter": 0.75,  # 1500 s over 2000 m
        "steps": "2400",
        "caloriesKcal": 120,
        "averageHeartRateBeatsPerMinute": "101",
        "heartRateZoneDurations": {
            "lightTime": "600s",
            "moderateTime": "300s",
            "vigorousTime": "60s",
            "peakTime": "0s",
        },
        "activeZoneMinutes": "12",
    }
    assert summary(WORKOUT | {"measured": reading})["distanceMillimeters"] == 1_800_000


def test_speed_for_bikes_and_swims_pace_on_foot_neither_for_court_sports():
    ride = summary(WORKOUT | {"exerciseType": "BIKING", "distanceKm": 9.0})
    assert ride == {"distanceMillimeters": 9_000_000, "averageSpeedMillimetersPerSecond": 6000.0}
    tennis = summary(WORKOUT | {"exerciseType": "TENNIS", "distanceKm": 2.0})
    assert tennis == {"distanceMillimeters": 2_000_000}
    swim = Measured(status="measured", average_heart_rate=120, swim_lengths=24)
    pool = summary(WORKOUT | {"exerciseType": "SWIMMING_POOL", "measured": swim.model_dump()})
    assert pool["totalSwimLengths"] == 24


@pytest.mark.parametrize(
    ("exercise_type", "km", "ok"),
    [("RUNNING", 10.0, True), ("RUNNING", 11.0, False), ("WALKING", 4.0, True),
     ("WALKING", 5.0, False), ("BIKING", 30.0, True), ("BIKING", 35.0, False),
     ("SWIMMING", 4.5, False), ("TENNIS", 30.0, True)],
)  # fmt: skip
def test_speed_limits_follow_the_kind_of_workout(exercise_type, km, ok):
    log = WORKOUT | {"exerciseType": exercise_type, "distanceKm": km}  # 25 active minutes
    if ok:
        LOG.validate_python(log)
    else:
        with pytest.raises(ValidationError):
            LOG.validate_python(log)


@pytest.mark.parametrize("status", ["no_data", "unavailable"])
def test_without_a_reading_only_the_given_values_are_sent(status):
    assert summary(WORKOUT | {"measured": {"status": status}}) == {}


def test_a_supplied_reading_is_replaced_by_the_servers_own():
    forged = WORKOUT | {"exerciseType": "TENNIS", "measured": {"status": "measured"}}
    calls = []

    def measurer(start, end, exercise_type):
        calls.append((start, end, exercise_type))
        return READING

    payload = with_measurement(forged, measurer)
    assert payload["measured"]["caloriesKcal"] == 120
    assert calls == [(START, END, "TENNIS")]
    assert with_measurement(forged, None)["measured"] == {"status": "unavailable", "overlaps": []}


def test_food_and_invalid_workouts_are_not_measured():
    def measurer(start, end, exercise_type):
        raise AssertionError("Google should not be asked")

    food = {"kind": "food", "measured": {"status": "measured"}}
    assert with_measurement(food, measurer) == {"kind": "food"}
    invalid = WORKOUT | {"endTime": WORKOUT["startTime"]}
    assert "measured" not in with_measurement(invalid, measurer)


def test_kinds_are_as_seen_on_the_owners_workouts():
    # Fitbit's own summaries: walks have steps, distance and pace; soccer, tennis, volleyball
    # and "sport" steps and distance; the elliptical steps; gym work neither.
    assert exercises.kind("WALKING") == Kind.ON_FOOT
    for exercise_type in ("SOCCER", "TENNIS", "VOLLEYBALL", "SPORT"):
        assert exercises.kind(exercise_type) == Kind.FIELD
    assert exercises.kind("ELLIPTICAL") == Kind.STEPS
    for exercise_type in ("WEIGHTLIFTING", "STRENGTH_TRAINING", "CARDIO_WORKOUT", "WORKOUT"):
        assert exercises.kind(exercise_type) == Kind.OTHER


@pytest.fixture
def sessions(tmp_path):
    config = Config("alembic.ini")
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    with Session(engine) as db:
        person = User(email="first@example.com")
        db.add(person)
        db.commit()
        person_id = person.id

    @contextmanager
    def scope():
        with Session(engine) as db:
            yield db
            db.commit()

    return scope, person_id


def test_the_model_cannot_supply_the_reading_and_repeats_stay_one_draft(sessions):
    scope, person = sessions
    readings = [READING, READING.model_copy(update={"steps": 2500})]
    question = uuid.uuid4()
    tools = proposal_tools(
        scope, person, question, datetime.now(UTC), [], lambda s, e, k: readings.pop(0)
    )
    tool = tools["activity"][0]
    assert "measured" not in tool.parameters["properties"]
    assert "$defs" not in tool.parameters
    assert "TENNIS" in tool.parameters["properties"]["exerciseType"]["enum"]
    forged = WORKOUT | {"measured": {"status": "measured", "caloriesKcal": 9000}}
    first = json.loads(tool.run(forged)[0])
    assert first["log"]["measured"]["caloriesKcal"] == 120
    # The same request again, after more data synced, returns the same draft, not a conflict.
    second = json.loads(tool.run(WORKOUT)[0])
    assert second["draft_id"] == first["draft_id"]
