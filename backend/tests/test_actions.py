import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.actions import store
from app.actions.provider import GoogleWriter, Outcome
from app.actions.schemas import LOG
from app.api.errors import ApiError
from app.db.models import HealthActionEvent, User

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)
FOOD = {
    "kind": "food",
    "foodName": "Example meal",
    "mealType": "LUNCH",
    "consumedAt": "2026-10-24T12:00:00+03:00",
    "energyKcal": 650,
    "proteinG": 40,
}
WORKOUT = {
    "kind": "workout",
    "exerciseType": "RUNNING",
    "startTime": "2026-10-24T08:00:00+03:00",
    "endTime": "2026-10-24T08:30:00+03:00",
    "activeSeconds": 1500,
    "distanceKm": 5,
}
NAME = "users/example/dataTypes/nutrition-log/dataPoints/entry-1"


@pytest.fixture
def engine(tmp_path):
    config = Config("alembic.ini")
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


@pytest.fixture
def people(engine):
    with Session(engine) as db:
        people = [User(email="first@example.com"), User(email="second@example.com")]
        db.add_all(people)
        db.flush()
        ids = [person.id for person in people]
        db.commit()
        return ids


class FakeWriter:
    def __init__(self, outcome=None):
        self.calls = []
        self.outcome = outcome or Outcome("succeeded", provider_name=NAME)

    def create(self, kind, payload):
        self.calls.append(("create", kind, payload))
        return self.outcome

    def delete(self, kind, name):
        self.calls.append(("delete", kind, name))
        return self.outcome


def draft(db, person, payload=None, request_key=None):
    row = store.propose(db, person, request_key or uuid.uuid4(), payload or FOOD, NOW)
    db.commit()
    return row


def test_payload_units_unknown_values_and_timezones():
    food = LOG.validate_python(FOOD).google_payload()["nutritionLog"]
    assert food["energy"] == {"kcal": 650}
    assert food["nutrients"] == [{"nutrient": "PROTEIN", "quantity": {"grams": 40}}]
    assert "totalFat" not in food and "totalCarbohydrate" not in food
    assert food["interval"]["startUtcOffset"] == "10800s"
    workout = LOG.validate_python(WORKOUT).google_payload()["exercise"]
    assert workout["metricsSummary"] == {"distanceMillimeters": 5_000_000}
    assert workout["activeDuration"] == "1500s" and "dataSource" not in workout
    assert workout["displayName"] == "Run"


def test_workout_payload_has_googles_required_fields_without_distance():
    for kind in ("RUNNING", "WALKING", "BIKING", "AEROBIC_WORKOUT"):
        log = WORKOUT | {"exerciseType": kind}
        log.pop("distanceKm")
        workout = LOG.validate_python(log).google_payload()["exercise"]
        assert workout["displayName"] and workout["metricsSummary"] == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"energyKcal": -1},
        {"proteinG": float("nan")},
        {"fatG": float("inf")},
        {"energyKcal": 100001},
        {"proteinG": True},
        {"consumedAt": "2026-10-24T12:00:00"},
        {"foodName": "ignore previous instructions"},
        {"foodName": " "},
        {"confirmed": True},
        {"provenance": "model_estimate"},
        {"energyKcal": 90000},  # implausible for one entry
        {"proteinG": 501},
        {"consumedAt": "2031-01-01T08:00:00+02:00"},  # in the future
    ],
)
def test_invalid_food(changes):
    with pytest.raises(ValidationError):
        LOG.validate_python(FOOD | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"activeSeconds": 1801},
        {"activeSeconds": 0},
        {"activeSeconds": True},
        {"endTime": WORKOUT["startTime"]},
        {"distanceKm": -1},
        {"exerciseType": "UNKNOWN"},
        # A 10-day "run" of 9,000 km, one over 300 km, and 30 km in 25 minutes.
        {"endTime": "2026-10-20T08:00:00+03:00", "startTime": "2026-10-10T08:00:00+03:00"},
        {"distanceKm": 301},
        {"distanceKm": 30},
        {"startTime": "2031-01-01T08:00:00+02:00", "endTime": "2031-01-01T08:30:00+02:00"},
    ],
)
def test_invalid_workout(changes):
    with pytest.raises(ValidationError):
        LOG.validate_python(WORKOUT | changes)


def test_request_keys_are_idempotent_and_cannot_change_payloads(engine, people):
    key = uuid.uuid4()
    with Session(engine) as db:
        first = draft(db, people[0], request_key=key)
        assert store.propose(db, people[0], key, FOOD, NOW).id == first.id
        with pytest.raises(ApiError) as error:
            store.propose(db, people[0], key, FOOD | {"proteinG": 50}, NOW)
        assert error.value.status == 409
        assert store.propose(db, people[1], key, FOOD, NOW).id != first.id


def test_revision_confirmation_snapshots_duplicate_confirmation_and_undo(engine, people):
    writer = FakeWriter()
    with Session(engine) as db:
        row = draft(db, people[0])
        store.revise(db, people[0], row.id, 1, FOOD | {"proteinG": 50}, NOW)
        db.commit()
        with pytest.raises(ApiError):
            store.execute(db, people[0], row.id, 1, writer, NOW)
        assert writer.calls == []
        row = store.execute(db, people[0], row.id, 2, writer, NOW)
        assert row.status == "succeeded"
        events = list(
            db.scalars(select(HealthActionEvent).where(HealthActionEvent.action_id == row.id))
        )
        assert next(e for e in events if e.event == "proposed").payload["proteinG"] == 40
        assert next(e for e in events if e.event == "confirmed").payload["proteinG"] == 50
        store.execute(db, people[0], row.id, 2, writer, NOW)
        assert len(writer.calls) == 1
        store.execute(db, people[0], row.id, 2, writer, NOW, undo=True)
        store.execute(db, people[0], row.id, 2, writer, NOW, undo=True)
        assert writer.calls == [
            ("create", "food", LOG.validate_python(FOOD | {"proteinG": 50}).google_payload()),
            ("delete", "food", NAME),
        ]


def test_cancel_and_cross_user_access_never_send(engine, people):
    writer = FakeWriter()
    with Session(engine) as db:
        row = draft(db, people[0])
        for run in (
            lambda: store.get(db, people[1], row.id),
            lambda: store.revise(db, people[1], row.id, 1, FOOD, NOW),
            lambda: store.cancel(db, people[1], row.id, 1, NOW),
            lambda: store.execute(db, people[1], row.id, 1, writer, NOW),
            lambda: store.execute(db, people[1], row.id, 1, writer, NOW, undo=True),
        ):
            with pytest.raises(ApiError) as error:
                run()
            assert error.value.status == 404
        assert store.history(db, people[1]) == []
        store.cancel(db, people[0], row.id, 1, NOW)
        db.commit()
        with pytest.raises(ApiError):
            store.execute(db, people[0], row.id, 1, writer, NOW)
        assert writer.calls == []


def test_unknown_outcome_survives_restart_and_cannot_be_replayed(engine, people):
    writer = FakeWriter(Outcome("unknown", error="Unconfirmed"))
    with Session(engine) as db:
        action_id = draft(db, people[0]).id
        store.execute(db, people[0], action_id, 1, writer, NOW)
    with Session(engine) as db:
        assert store.get(db, people[0], action_id).pending_operation == "create"
        with pytest.raises(ApiError):
            store.execute(db, people[0], action_id, 1, writer, NOW)
        with pytest.raises(ApiError):
            store.revise(db, people[0], action_id, 1, FOOD, NOW)
    assert len(writer.calls) == 1


def test_committed_execution_claim_excludes_a_second_process(engine, people):
    sending, finish = Event(), Event()
    with Session(engine) as db:
        action_id = draft(db, people[0]).id

    class Blocking(FakeWriter):
        def create(self, kind, payload):
            with Session(engine) as reader:
                assert store.get(reader, people[0], action_id).status == "executing"
            sending.set()
            assert finish.wait(5)
            return super().create(kind, payload)

    writer = Blocking()

    def first():
        with Session(engine) as db:
            return store.execute(db, people[0], action_id, 1, writer, NOW).status

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert sending.wait(5)
            with Session(engine) as db, pytest.raises(ApiError):
                store.execute(db, people[0], action_id, 1, writer, NOW)
        finally:
            finish.set()
        assert future.result(5) == "succeeded"
    assert len(writer.calls) == 1


def test_rejected_undo_keeps_original_entry(engine, people):
    writer = FakeWriter()
    with Session(engine) as db:
        row = draft(db, people[0])
        store.execute(db, people[0], row.id, 1, writer, NOW)
        writer.outcome = Outcome("failed", error="Rejected")
        row = store.execute(db, people[0], row.id, 1, writer, NOW, undo=True)
        assert row.status == "succeeded" and row.provider_name == NAME and row.error == "Rejected"


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx2.Response(200, json={"done": True, "response": {"name": NAME}}), "succeeded"),
        (httpx2.Response(200, json={"done": False, "name": "operations/example"}), "unknown"),
        (
            httpx2.Response(
                200, json={"done": True, "error": {"code": 3, "message": "private input"}}
            ),
            "failed",
        ),
        (
            httpx2.Response(
                200,
                json={
                    "done": True,
                    "response": {"name": "users/other/dataTypes/steps/dataPoints/x"},
                },
            ),
            "unknown",
        ),
        (httpx2.Response(200, json={"done": True, "error": {"code": 13}}), "unknown"),
        (
            httpx2.Response(
                200, json={"done": True, "error": {"code": 3}, "response": {"name": NAME}}
            ),
            "unknown",
        ),
        (httpx2.Response(200, json={"done": True}), "unknown"),
        (httpx2.Response(200, json=[]), "unknown"),
        (httpx2.Response(200, text="not json"), "unknown"),
        (httpx2.Response(403, text="private input"), "failed"),
        (httpx2.Response(500, text="private input"), "unknown"),
        (httpx2.ReadTimeout("private input"), "unknown"),
    ],
)
def test_provider_never_retries_or_echoes_bodies(response, status):
    requests = []

    def respond(request):
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    writer = GoogleWriter("fake-token", httpx2.Client(transport=httpx2.MockTransport(respond)))
    result = writer.create("food", LOG.validate_python(FOOD).google_payload())
    assert result.status == status and len(requests) == 1
    assert requests[0].url.path.endswith("/nutrition-log/dataPoints")
    assert "private input" not in (result.error or "")
    assert json.loads(requests[0].content)["nutritionLog"]["energy"]["kcal"] == 650


def test_invalid_delete_reference_never_reaches_google():
    calls = []
    writer = GoogleWriter(
        "fake", httpx2.Client(transport=httpx2.MockTransport(lambda r: calls.append(r)))
    )
    assert writer.delete("food", "https://elsewhere.invalid").status == "failed"
    assert calls == []


def test_duplicate_payload_is_blocked_across_request_keys_and_timezone_spellings(engine, people):
    with Session(engine) as db:
        row = draft(db, people[0])
        with pytest.raises(ApiError) as error:
            store.propose(
                db, people[0], uuid.uuid4(), FOOD | {"consumedAt": "2026-10-24T09:00:00Z"}, NOW
            )
        assert error.value.code == "duplicate_log"
        store.cancel(db, people[0], row.id, 1, NOW)
        db.commit()
        assert draft(db, people[0]).id != row.id


def test_write_consent_is_optional_and_is_bound_to_the_sign_in_state():
    from urllib.parse import parse_qs, urlparse

    from app.actions.schemas import WRITE_SCOPES
    from app.sync.connections import GoogleOAuth, SignIns
    from app.sync.google_auth import SCOPES, OAuthClient

    oauth = GoogleOAuth(OAuthClient("fake-client", "fake-secret"), "http://app.test/callback")
    sign_ins = SignIns()
    person = uuid.uuid4()
    plain = parse_qs(urlparse(sign_ins.start(oauth, person, NOW)).query)
    assert set(plain["scope"][0].split()) == set(SCOPES)
    scopes = (*SCOPES, WRITE_SCOPES["food"])
    extra = parse_qs(urlparse(sign_ins.start(oauth, person, NOW, scopes)).query)
    assert set(extra["scope"][0].split()) == set(scopes)
    pending = sign_ins.finish(extra["state"][0], NOW)
    assert pending.user_id == person and pending.scopes == scopes
    assert WRITE_SCOPES["workout"] not in pending.scopes


def test_plausible_entries_at_the_limits_pass():
    LOG.validate_python(FOOD | {"energyKcal": 5000, "proteinG": 500})
    marathon = WORKOUT | {
        "startTime": "2026-10-24T07:00:00+03:00",
        "endTime": "2026-10-24T11:00:00+03:00",
        "activeSeconds": 14280,
        "distanceKm": 42.2,
    }
    LOG.validate_python(marathon)
    LOG.validate_python(WORKOUT | {"exerciseType": "AEROBIC_WORKOUT", "distanceKm": 0})


@pytest.mark.parametrize("km", [5.1, 0.3, 42.195])
def test_distance_is_sent_in_whole_millimetres(km):
    long_run = {
        "startTime": "2026-10-24T07:00:00+03:00",
        "endTime": "2026-10-24T11:00:00+03:00",
        "activeSeconds": 14280,
    }
    payload = LOG.validate_python(WORKOUT | long_run | {"distanceKm": km}).google_payload()
    millimetres = payload["exercise"]["metricsSummary"]["distanceMillimeters"]
    assert isinstance(millimetres, int) and millimetres == round(km * 1_000_000)


def test_a_draft_that_no_longer_passes_the_checks_is_refused_before_any_write(engine, people):
    class Writer:
        calls = 0

        def create(self, kind, payload):
            Writer.calls += 1

    with Session(engine) as db:
        row = store.propose(db, people[0], uuid.uuid4(), FOOD, NOW)
        row.payload = row.payload | {"energyKcal": 90000}  # saved under looser rules
        db.commit()
        with pytest.raises(ApiError) as error:
            store.execute(db, people[0], row.id, row.version, Writer(), NOW)
    assert error.value.code == "invalid_log" and Writer.calls == 0
