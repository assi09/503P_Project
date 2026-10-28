from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.api import auth
from app.api.main import create_app
from app.auth.accounts import LoginThrottle
from app.db.models import Reminder, User
from app.db.session import session_scope
from app.reminders import store

PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)  # 11:00 in Beirut
NIGHTS = {"kind": "weekly", "time": "22:30", "weekdays": [0, 1, 2, 3, 4]}


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


@pytest.fixture
def client(engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "throttle", LoginThrottle())
    app = create_app()

    def db():
        with session_scope(engine) as session:
            yield session

    app.dependency_overrides[auth.get_db] = db
    app.dependency_overrides[auth.now] = lambda: NOW
    return TestClient(app)


def signed_in(client, engine, email="person@example.com", approved=True) -> dict:
    token = client.post("/auth/signup", json={"email": email, "password": PASSWORD}).json()["token"]
    if approved:
        with session_scope(engine) as session:
            session.scalar(select(User).where(User.email == email)).status = "approved"
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.put("/me/timezone", json={"timezone": "Asia/Beirut"}, headers=headers).status_code
        == 204
    )
    return headers


def signed_up(client, email: str) -> dict:
    """Signed up but not approved yet."""
    body = {"email": email, "password": PASSWORD}
    return {"Authorization": f"Bearer {client.post('/auth/signup', json=body).json()['token']}"}


def create(client, headers, **changes):
    body = {"title": "Wind down", "message": "Screens off soon.", "schedule": NIGHTS} | changes
    return client.post("/reminders", json=body, headers=headers)


def test_reminders_need_an_approved_account(client, engine):
    assert client.get("/reminders").status_code == 401
    pending = signed_up(client, "new@example.com")
    assert client.get("/reminders", headers=pending).status_code == 403


def test_a_persons_own_reminder_is_active_and_due_in_their_time_zone(client, engine):
    headers = signed_in(client, engine)
    reminder = create(client, headers).json()
    assert reminder["status"] == "active" and reminder["source"] == "person"
    assert reminder["scheduleText"] == "Weeknights at 22:30"
    assert reminder["timezone"] == "Asia/Beirut"
    assert reminder["channels"] == ["email", "in_app"]
    # Wednesday 22:30 in Beirut (UTC+2 after Oct 25) is 20:30 UTC.
    assert reminder["nextDueAt"].startswith("2026-10-28T20:30")
    assert [r["id"] for r in client.get("/reminders", headers=headers).json()] == [reminder["id"]]


@pytest.mark.parametrize(
    "changes, code",
    [
        ({"title": ""}, 422),
        ({"title": "x" * 81}, 422),
        ({"channels": []}, 422),
        ({"channels": ["sms"]}, 422),
        ({"schedule": {"kind": "weekly", "time": "25:00", "weekdays": [0]}}, 422),
        ({"schedule": {"kind": "weekly", "time": "08:00", "weekdays": []}}, 422),
        ({"schedule": {"kind": "monthly", "time": "08:00"}}, 422),
        ({"schedule": {"kind": "once", "date": "2026-10-27", "time": "08:00"}}, 422),
    ],
)
def test_bad_reminders_are_refused(client, engine, changes, code):
    response = create(client, signed_in(client, engine), **changes)
    assert response.status_code == code
    assert "error" in response.json()


def test_a_one_off_already_past_says_so(client, engine):
    past = {"kind": "once", "date": "2026-10-28", "time": "08:00"}  # 08:00 Beirut, before NOW
    response = create(client, signed_in(client, engine), schedule=past)
    assert response.json()["error"]["code"] == "in_the_past"


def test_pausing_resuming_and_editing_keep_the_version_honest(client, engine):
    headers = signed_in(client, engine)
    reminder = create(client, headers).json()
    url = f"/reminders/{reminder['id']}"
    paused = client.patch(url, json={"version": 1, "status": "paused"}, headers=headers).json()
    assert paused["status"] == "paused" and paused["nextDueAt"] is None and paused["version"] == 2
    stale = client.patch(url, json={"version": 1, "status": "active"}, headers=headers)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "version_conflict"
    resumed = client.patch(
        url,
        json={"version": 2, "status": "active", "schedule": {**NIGHTS, "time": "23:00"}},
        headers=headers,
    ).json()
    assert resumed["scheduleText"] == "Weeknights at 23:00"
    assert resumed["nextDueAt"].startswith("2026-10-28T21:00")


def test_a_proposed_reminder_waits_for_approval(client, engine):
    headers = signed_in(client, engine)
    with session_scope(engine) as session:
        user = session.scalar(select(User))
        row = store.create(
            session,
            user,
            title="Wind down",
            message="Later bedtimes went with lower sleep efficiency.",
            schedule=NIGHTS,
            channels=["in_app"],
            now=NOW,
            source="agent",
            reason="Later bedtimes went with lower efficiency.",
        )
        assert row.status == "proposed" and row.next_due_at is None
        reminder_id = str(row.id)
    url = f"/reminders/{reminder_id}"
    # A proposal cannot be paused: only approved or declined.
    refused = client.patch(url, json={"version": 1, "status": "paused"}, headers=headers)
    assert refused.status_code == 409
    approved = client.patch(url, json={"version": 1, "status": "active"}, headers=headers).json()
    assert approved["status"] == "active" and approved["nextDueAt"] is not None
    assert approved["source"] == "agent" and approved["reason"]


def test_a_declined_or_deleted_reminder_cannot_come_back(client, engine):
    headers = signed_in(client, engine)
    first = create(client, headers).json()
    assert client.delete(f"/reminders/{first['id']}", headers=headers).status_code == 204
    assert client.get("/reminders", headers=headers).json() == []
    again = client.patch(f"/reminders/{first['id']}", json={"version": 2}, headers=headers)
    assert again.status_code == 404


def test_nobody_sees_or_changes_anyone_elses_reminders(client, engine):
    owner = signed_in(client, engine)
    reminder = create(client, owner).json()
    other = signed_in(client, engine, email="other@example.com")
    assert client.get("/reminders", headers=other).json() == []
    url = f"/reminders/{reminder['id']}"
    assert (
        client.patch(url, json={"version": 1, "status": "paused"}, headers=other).status_code == 404
    )
    assert client.delete(url, headers=other).status_code == 404


def test_moving_time_zone_moves_the_reminders_still_to_come(client, engine):
    headers = signed_in(client, engine)
    reminder = create(client, headers).json()
    client.put("/me/timezone", json={"timezone": "Europe/London"}, headers=headers)
    moved = client.get("/reminders", headers=headers).json()[0]
    assert moved["id"] == reminder["id"] and moved["timezone"] == "Europe/London"
    assert moved["nextDueAt"].startswith("2026-10-28T22:30")  # London is UTC in winter
    bad = client.put("/me/timezone", json={"timezone": "Mars/Olympus"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_timezone"


def test_notification_settings_have_defaults_and_keep_changes(client, engine):
    headers = signed_in(client, engine)
    defaults = client.get("/notification-settings", headers=headers).json()
    assert defaults == {
        "quietHours": {"start": "22:00", "end": "07:00"},
        "maxPerDay": 3,
        "email": True,
    }
    changed = {"quietHours": None, "maxPerDay": 2, "email": False}
    assert client.put("/notification-settings", json=changed, headers=headers).json() == changed
    assert client.get("/notification-settings", headers=headers).json() == changed
    bad = client.put(
        "/notification-settings",
        json={"quietHours": {"start": "9pm", "end": "07:00"}, "maxPerDay": 0, "email": True},
        headers=headers,
    )
    assert bad.status_code == 422


def test_reminders_are_stored_with_a_valid_schedule(client, engine):
    headers = signed_in(client, engine)
    create(client, headers)
    with session_scope(engine) as session:
        row = session.scalar(select(Reminder))
        assert store.schedule_of(row).weekdays == [0, 1, 2, 3, 4]
