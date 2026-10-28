from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.api import auth
from app.api.main import create_app
from app.auth.accounts import LoginThrottle
from app.db.models import Notification, Reminder, ReminderDelivery, User
from app.db.session import session_scope
from app.email import MailError
from app.reminders import store
from app.reminders.deliver import compose, deliver_due

APP = "https://app.example.com"
PASSWORD = "correct horse battery"
# Wednesday 2026-10-28; Beirut is UTC+2 now.
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
NIGHTS = {"kind": "weekly", "time": "22:30", "weekdays": [0, 1, 2, 3, 4]}
DUE = datetime(2026, 10, 28, 20, 30, tzinfo=UTC)  # 22:30 in Beirut


class Mailbox:
    def __init__(self, fail: bool = False):
        self.sent, self.fail = [], fail

    def send(self, email) -> None:
        if self.fail:
            raise MailError("Resend refused the email (403): domain not verified")
        self.sent.append(email)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


def sessions(engine):
    return lambda: session_scope(engine)


def person(engine, email="person@example.com") -> str:
    with session_scope(engine) as db:
        user = User(email=email, status="approved", timezone="Asia/Beirut")
        db.add(user)
        db.flush()
        return str(user.id)


def reminder(engine, email="person@example.com", **options) -> str:
    """A reminder made through the store, as the API or the agent would."""
    with session_scope(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        row = store.create(
            db,
            user,
            title=options.pop("title", "Wind down"),
            message=options.pop("message", "Screens off soon."),
            schedule=options.pop("schedule", NIGHTS),
            channels=options.pop("channels", ["in_app", "email"]),
            now=NOW,
            source=options.pop("source", "person"),
        )
        if options.pop("approve", False):
            store.change(db, row, version=row.version, now=NOW, status="active")
        return str(row.id)


def deliveries(engine) -> list[tuple[str, str]]:
    with session_scope(engine) as db:
        return sorted((d.channel, d.status) for d in db.scalars(select(ReminderDelivery)))


def notifications(engine) -> int:
    with session_scope(engine) as db:
        return len(db.scalars(select(Notification)).all())


def test_a_due_reminder_arrives_in_the_app_and_by_email_once(engine):
    person(engine)
    reminder_id = reminder(engine)
    mail = Mailbox()
    assert deliver_due(sessions(engine), DUE - timedelta(minutes=1), mail, APP) == {}
    counts = deliver_due(sessions(engine), DUE, mail, APP)
    assert counts == {"sent": 2}
    assert notifications(engine) == 1 and len(mail.sent) == 1
    assert mail.sent[0].to == "person@example.com" and mail.sent[0].subject == "Wind down"
    # The same minute again sends nothing: it is due tomorrow now.
    assert deliver_due(sessions(engine), DUE, mail, APP) == {}
    with session_scope(engine) as db:
        assert store.utc(db.get(Reminder, reminder_id_uuid(reminder_id)).next_due_at) == (
            DUE + timedelta(days=1)
        )


def reminder_id_uuid(value: str):
    import uuid

    return uuid.UUID(value)


def test_a_one_off_is_done_after_it_is_sent(engine):
    person(engine)
    reminder_id = reminder(engine, schedule={"kind": "once", "date": "2026-10-29", "time": "07:00"})
    deliver_due(sessions(engine), datetime(2026, 10, 29, 5, 0, tzinfo=UTC), Mailbox(), APP)
    with session_scope(engine) as db:
        row = db.get(Reminder, reminder_id_uuid(reminder_id))
        assert row.status == "done" and row.next_due_at is None


def test_paused_and_proposed_reminders_are_not_sent(engine):
    person(engine)
    paused = reminder(engine)
    with session_scope(engine) as db:
        row = db.get(Reminder, reminder_id_uuid(paused))
        store.change(db, row, version=row.version, now=NOW, status="paused")
    reminder(engine, source="agent")  # proposed, never approved
    assert deliver_due(sessions(engine), DUE, Mailbox(), APP) == {}


def test_email_turned_off_still_sends_in_the_app(engine):
    user_id = person(engine)
    with session_scope(engine) as db:
        store.save_notification_settings(
            db, reminder_id_uuid(user_id), quiet=None, max_per_day=3, email=False, now=NOW
        )
    reminder(engine)
    mail = Mailbox()
    deliver_due(sessions(engine), DUE, mail, APP)
    assert deliveries(engine) == [("email", "skipped_off"), ("in_app", "sent")]
    assert mail.sent == [] and notifications(engine) == 1


def test_a_failed_email_is_recorded_and_the_app_still_gets_it(engine):
    person(engine)
    reminder(engine)
    counts = deliver_due(sessions(engine), DUE, Mailbox(fail=True), APP)
    assert counts == {"sent": 1, "failed": 1}
    with session_scope(engine) as db:
        failed = db.scalar(select(ReminderDelivery).where(ReminderDelivery.status == "failed"))
        assert "domain not verified" in failed.error
    assert notifications(engine) == 1


def test_a_reminder_missed_while_the_server_was_down_is_skipped_not_sent_late(engine):
    person(engine)
    reminder(engine)
    mail = Mailbox()
    late = DUE + timedelta(hours=3)
    assert deliver_due(sessions(engine), late, mail, APP) == {"skipped_late": 2}
    assert mail.sent == [] and notifications(engine) == 0
    with session_scope(engine) as db:
        assert store.utc(db.scalar(select(Reminder)).next_due_at) == DUE + timedelta(days=1)


def test_quiet_hours_hold_back_suggestions_but_not_your_own_reminders(engine):
    person(engine)  # default quiet hours 22:00-07:00
    reminder(engine, title="Mine")
    reminder(engine, title="Suggested", source="agent", approve=True)
    deliver_due(sessions(engine), DUE, Mailbox(), APP)
    with session_scope(engine) as db:
        by_title = {
            r.title: {
                d.status
                for d in db.scalars(
                    select(ReminderDelivery).where(ReminderDelivery.reminder_id == r.id)
                )
            }
            for r in db.scalars(select(Reminder))
        }
    assert by_title == {"Mine": {"sent"}, "Suggested": {"skipped_quiet"}}


def test_suggestions_stop_at_the_daily_cap(engine):
    user_id = person(engine)
    with session_scope(engine) as db:
        store.save_notification_settings(
            db, reminder_id_uuid(user_id), quiet=None, max_per_day=1, email=True, now=NOW
        )
    afternoon = {"kind": "weekly", "time": "15:00", "weekdays": list(range(7))}
    for title in ("First", "Second"):
        reminder(
            engine,
            title=title,
            source="agent",
            approve=True,
            schedule=afternoon,
            channels=["in_app"],
        )
    deliver_due(sessions(engine), datetime(2026, 10, 28, 13, 0, tzinfo=UTC), Mailbox(), APP)
    assert deliveries(engine) == [("in_app", "sent"), ("in_app", "skipped_cap")]


def test_two_copies_of_the_server_never_send_the_same_reminder_twice(engine):
    user_id = person(engine)
    reminder_id = reminder(engine)
    # The other copy already claimed this send.
    with session_scope(engine) as db:
        db.add(
            ReminderDelivery(
                reminder_id=reminder_id_uuid(reminder_id),
                user_id=reminder_id_uuid(user_id),
                due_at=DUE,
                channel="in_app",
                status="sent",
            )
        )
    mail = Mailbox()
    assert deliver_due(sessions(engine), DUE, mail, APP) == {"already_delivered": 1}
    assert mail.sent == [] and notifications(engine) == 0


def test_the_email_escapes_what_the_person_wrote(engine):
    person(engine)
    reminder(engine, message="<script>alert(1)</script> & stretch")
    with session_scope(engine) as db:
        email = compose(db.scalar(select(Reminder)), db.scalar(select(User)), APP)
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html
    assert f"{APP}/reminders" in email.text


# The inbox


@pytest.fixture
def client(engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "throttle", LoginThrottle())
    app = create_app()

    def db():
        with session_scope(engine) as session:
            yield session

    app.dependency_overrides[auth.get_db] = db
    app.dependency_overrides[auth.now] = lambda: DUE
    return TestClient(app)


def signed_in(client, engine, email) -> dict:
    token = client.post("/auth/signup", json={"email": email, "password": PASSWORD}).json()["token"]
    with session_scope(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        user.status, user.timezone = "approved", "Asia/Beirut"
    return {"Authorization": f"Bearer {token}"}


def test_the_inbox_shows_due_reminders_and_marks_them_read(client, engine):
    headers = signed_in(client, engine, "person@example.com")
    reminder(engine)
    deliver_due(sessions(engine), DUE, Mailbox(), APP)
    inbox = client.get("/notifications", headers=headers).json()
    assert inbox["unread"] == 1
    [item] = inbox["items"]
    assert item["title"] == "Wind down" and item["link"] == "/reminders" and item["readAt"] is None
    read = client.post(f"/notifications/{item['id']}/read", headers=headers).json()
    assert read["readAt"] is not None
    assert client.get("/notifications", headers=headers).json()["unread"] == 0


def test_read_all_and_nobody_reads_anyone_elses_inbox(client, engine):
    owner = signed_in(client, engine, "person@example.com")
    other = signed_in(client, engine, "other@example.com")
    reminder(engine)
    deliver_due(sessions(engine), DUE, Mailbox(), APP)
    item = client.get("/notifications", headers=owner).json()["items"][0]
    assert client.get("/notifications", headers=other).json() == {"items": [], "unread": 0}
    assert client.post(f"/notifications/{item['id']}/read", headers=other).status_code == 404
    assert client.post("/notifications/read-all", headers=owner).status_code == 204
    assert client.get("/notifications", headers=owner).json()["unread"] == 0


def test_without_an_email_key_reminders_still_reach_the_app(engine, monkeypatch):
    from app.config import settings
    from app.reminders import loop

    monkeypatch.setattr(settings, "email_backend", "resend")
    monkeypatch.setattr(settings, "email_api_key", None)
    person(engine)
    reminder(engine)
    counts = deliver_due(sessions(engine), DUE, loop._mailer(), APP)
    assert counts == {"sent": 1, "failed": 1} and notifications(engine) == 1
