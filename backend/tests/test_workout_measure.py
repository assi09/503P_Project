import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.actions.measure import measure, with_measurement
from app.actions.schemas import LOG, Measured
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
READING = Measured(
    status="measured", steps=2400, distance_km=1.8, calories_kcal=120, average_heart_rate=101
)
ROLLUPS = {
    "heart-rate": {"heartRate": {"beatsPerMinuteAvg": 100.6, "beatsPerMinuteMax": 120}},
    "steps": {"steps": {"countSum": "2400"}},
    "distance": {"distance": {"millimetersSum": "1800000"}},
    "total-calories": {"totalCalories": {"kcalSum": 119.6}},
}


def exercise(kind, start, end):
    return {"exercise": {"exerciseType": kind, "interval": {"startTime": start, "endTime": end}}}


class FakeGoogle:
    """Answers the roll-ups and the exercise list by URL and records what was asked."""

    def __init__(self, rollups=None, exercises=(), status=200):
        self.rollups = ROLLUPS if rollups is None else rollups
        self.exercises = list(exercises)
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
        return httpx2.Response(200, json={"dataPoints": self.exercises})

    def client(self) -> HealthClient:
        http = httpx2.Client(transport=httpx2.MockTransport(self))
        return HealthClient(lambda: "token", http=http, max_retries=0)


def test_measures_the_workout_interval_like_fitbit_does():
    google = FakeGoogle()
    measured = measure(google.client(), START, END)
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


def test_no_heart_rate_means_no_tracker_data_and_no_resting_calories():
    google = FakeGoogle(rollups={"total-calories": ROLLUPS["total-calories"]})
    measured = measure(google.client(), START, END)
    assert measured == Measured(status="no_data")
    assert not any("total-calories" in str(r.url) for r in google.requests)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_google_failures_leave_the_draft_unmeasured(status):
    assert measure(FakeGoogle(status=status).client(), START, END) == Measured(status="unavailable")


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
    overlaps = measure(google.client(), START, END).overlaps
    assert [o.exercise_type for o in overlaps] == ["WALKING"]


def test_the_persons_values_win_and_the_tracker_fills_in_the_rest():
    log = WORKOUT | {"distanceKm": 2.0, "measured": READING.model_dump(by_alias=True)}
    summary = LOG.validate_python(log).google_payload()["exercise"]["metricsSummary"]
    assert summary == {
        "distanceMillimeters": 2_000_000,  # what the person said, not the measured 1.8 km
        "averagePaceSecondsPerMeter": 0.75,  # 1500 s over 2000 m
        "steps": "2400",
        "caloriesKcal": 120,
        "averageHeartRateBeatsPerMinute": "101",
    }
    measured_only = WORKOUT | {"measured": READING.model_dump(by_alias=True)}
    summary = LOG.validate_python(measured_only).google_payload()["exercise"]["metricsSummary"]
    assert summary["distanceMillimeters"] == 1_800_000


@pytest.mark.parametrize("status", ["no_data", "unavailable"])
def test_without_a_reading_only_the_given_values_are_sent(status):
    log = WORKOUT | {"measured": {"status": status}}
    summary = LOG.validate_python(log).google_payload()["exercise"]["metricsSummary"]
    assert summary == {}


def test_a_supplied_reading_is_replaced_by_the_servers_own():
    forged = WORKOUT | {"measured": {"status": "measured", "caloriesKcal": 9000}}
    calls = []

    def measurer(start, end):
        calls.append((start, end))
        return READING

    payload = with_measurement(forged, measurer)
    assert payload["measured"]["caloriesKcal"] == 120
    assert calls == [(START, END)]
    assert with_measurement(forged, None)["measured"] == {"status": "unavailable", "overlaps": []}


def test_food_and_invalid_workouts_are_not_measured():
    def measurer(start, end):
        raise AssertionError("Google should not be asked")

    food = {"kind": "food", "measured": {"status": "measured"}}
    assert with_measurement(food, measurer) == {"kind": "food"}
    invalid = WORKOUT | {"endTime": WORKOUT["startTime"]}
    assert "measured" not in with_measurement(invalid, measurer)


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
        scope, person, question, datetime.now(UTC), [], lambda s, e: readings.pop(0)
    )
    tool = tools["activity"][0]
    assert "measured" not in tool.parameters["properties"]
    assert "$defs" not in tool.parameters
    forged = WORKOUT | {"measured": {"status": "measured", "caloriesKcal": 9000}}
    first = json.loads(tool.run(forged)[0])
    assert first["log"]["measured"]["caloriesKcal"] == 120
    # The same request again, after more data synced, returns the same draft, not a conflict.
    second = json.loads(tool.run(WORKOUT)[0])
    assert second["draft_id"] == first["draft_id"]
