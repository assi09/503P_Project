import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app import background
from app.alarms import run
from app.analysis.day import with_scores
from app.api import auth
from app.api.main import create_app
from app.auth.accounts import LoginThrottle
from app.db.chat import load_evidence
from app.db.daily import save_daily
from app.db.models import Alarm, GoogleConnection, Notification, SyncRun, User
from app.db.session import session_scope
from app.email import MailError
from app.reminders import store
from app.synthetic import Step, generate

APP = "https://app.example.com"
PASSWORD = "correct horse battery"
START = date(2026, 7, 1)
LAST = START + timedelta(days=89)  # 2026-09-28, the last day of data
NOON = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)  # 13:00 in Beirut, outside quiet hours
NIGHT = datetime(2026, 9, 28, 21, 0, tzinfo=UTC)  # midnight in Beirut, in quiet hours


class Mailbox:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, email):
        if self.fail:
            raise MailError("Resend is down")
        self.sent.append(email)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


def bad_night_frame(seed=3):
    return generate(START, 90, (Step("sleep_minutes", LAST, -240),), seed=seed).frame


def person(engine, email="person@example.com", frame=None, status="active") -> uuid.UUID:
    with session_scope(engine) as db:
        user = User(email=email, status="approved", timezone="Asia/Beirut")
        db.add(user)
        db.flush()
        db.add(GoogleConnection(user_id=user.id, encrypted_token=b"x", status=status))
        save_daily(db, user.id, "google_health", bad_night_frame() if frame is None else frame)
        return user.id


def alarms(engine):
    with session_scope(engine) as db:
        return [(a.key, a.status, a.reason) for a in db.scalars(select(Alarm))]


def sessions(engine):
    return lambda: session_scope(engine)


def test_a_bad_night_is_checked_stored_with_its_evidence_and_sent_once(engine):
    user_id = person(engine)
    mail = Mailbox()
    counts = run.run_all(sessions(engine), NOON, mail, APP)
    assert counts["created"] >= 1 and counts["sent"] >= 1
    with session_scope(engine) as db:
        alarm = db.scalar(select(Alarm).where(Alarm.key == "day:sleep_minutes"))
        assert alarm.status == "sent" and alarm.title == "Time asleep well below your usual"
        assert "against your usual" in alarm.body
        # Its evidence is stored, so the alarm's link opens the numbers.
        assert set(load_evidence(db, user_id, alarm.evidence_ids)) == set(alarm.evidence_ids)
        note = db.scalar(select(Notification).where(Notification.kind == "alarm"))
        assert note.link == f"/evidence/{alarm.evidence_ids[0]}"
    assert any(e.subject == "Time asleep well below your usual" for e in mail.sent)
    # The next pass, and the next day, raise nothing new for the same thing (cooldown).
    run.run_all(sessions(engine), NOON + timedelta(minutes=15), mail, APP)
    run.run_all(sessions(engine), NOON + timedelta(days=1), mail, APP)
    assert [k for k, _, _ in alarms(engine)].count("day:sleep_minutes") == 1


def test_quiet_hours_hold_an_alarm_until_morning_and_old_ones_expire(engine):
    person(engine)
    run.run_all(sessions(engine), NIGHT, Mailbox(), APP)
    assert {s for _, s, _ in alarms(engine)} == {"pending"}
    morning = NIGHT + timedelta(hours=8)  # 08:00 in Beirut
    run.run_all(sessions(engine), morning, Mailbox(), APP)
    assert "sent" in {s for _, s, _ in alarms(engine)}
    with session_scope(engine) as db:
        db.add(
            Alarm(
                user_id=db.scalar(select(User)).id,
                kind="day",
                metric="hrv_ms",
                key="day:hrv_ms",
                day=LAST,
                severity=1.0,
                title="old",
                body="old",
                created_at=morning - timedelta(hours=13),
            )
        )
    run.run_all(sessions(engine), morning, Mailbox(), APP)
    assert ("day:hrv_ms", "expired", None) in alarms(engine)


def test_the_daily_limit_holds_back_the_rest(engine):
    user_id = person(engine)
    with session_scope(engine) as db:
        store.save_notification_settings(
            db, user_id, quiet=None, max_per_day=1, email=False, now=NOON
        )
        for metric in ("hrv_ms", "resting_hr"):
            db.add(
                Alarm(
                    user_id=user_id,
                    kind="day",
                    metric=metric,
                    key=f"day:{metric}",
                    day=LAST,
                    severity=0.5,
                    title=metric,
                    body=metric,
                    created_at=NOON,
                )
            )
    run.run_all(sessions(engine), NOON, Mailbox(), APP)
    statuses = sorted(s for _, s, _ in alarms(engine))
    assert statuses.count("sent") == 1
    assert ("day:hrv_ms", "suppressed", "daily_limit") in alarms(engine)


def test_muted_kinds_disabled_alarms_and_a_failed_email(engine):
    user_id = person(engine)
    with session_scope(engine) as db:
        run.save_settings(
            db, user_id, enabled=True, muted_kinds=["day"], sensitivity="normal", now=NOON
        )
    run.run_all(sessions(engine), NOON, Mailbox(), APP)
    assert not any(k.startswith("day:") for k, _, _ in alarms(engine))
    with session_scope(engine) as db:
        run.save_settings(
            db, user_id, enabled=False, muted_kinds=[], sensitivity="normal", now=NOON
        )
    before = len(alarms(engine))
    run.run_all(sessions(engine), NOON + timedelta(days=4), Mailbox(), APP)
    assert len(alarms(engine)) == before
    with session_scope(engine) as db:
        run.save_settings(db, user_id, enabled=True, muted_kinds=[], sensitivity="normal", now=NOON)
    counts = run.run_all(sessions(engine), NOON, Mailbox(fail=True), APP)
    assert counts["sent"] >= 1  # the in-app alarm still goes out


def test_an_expired_sign_in_and_stale_data_raise_their_own_alarm(engine):
    person(engine, status="reconnect_needed")
    run.run_all(sessions(engine), NOON, Mailbox(), APP)
    assert ("data:reconnect", "sent", None) in alarms(engine)
    with session_scope(engine) as db:
        assert (
            db.scalar(
                select(Notification).where(
                    Notification.kind == "alarm", Notification.title == "Reconnect Google Health"
                )
            ).link
            == "/settings"
        )


def test_one_person_failing_stops_no_one(engine, monkeypatch):
    person(engine, "a@example.com")
    person(engine, "b@example.com")
    real = run.check
    calls = []

    def flaky(db, user, *args, **kwargs):
        calls.append(user.email)
        if user.email == "a@example.com":
            raise RuntimeError("boom")
        return real(db, user, *args, **kwargs)

    monkeypatch.setattr(run, "check", flaky)
    counts = run.run_all(sessions(engine), NOON, Mailbox(), APP)
    assert counts["errors"] == 1 and counts["created"] >= 1 and len(calls) == 2


def test_alarm_text_never_has_advice():
    from app.agent.verifier import MEDICAL
    from app.alarms.detect import detect

    frame = with_scores(bad_night_frame())
    for candidate in detect(frame, LAST):
        title, body = run.text(candidate)
        assert not MEDICAL.search(title + body)
        assert "should" not in (title + body).lower()


def test_background_syncs_start_only_for_stale_connections(engine, monkeypatch):
    from app.api import google

    fresh = person(engine, "fresh@example.com")
    stale = person(engine, "stale@example.com")
    person(engine, "expired@example.com", status="reconnect_needed")
    with session_scope(engine) as db:
        db.add(
            SyncRun(
                user_id=fresh,
                source="google_health",
                status="succeeded",
                range_start=LAST,
                range_end=LAST,
                started_at=NOON - timedelta(hours=1),
            )
        )
        db.add(
            SyncRun(
                user_id=stale,
                source="google_health",
                status="succeeded",
                range_start=LAST,
                range_end=LAST,
                started_at=NOON - timedelta(hours=5),
            )
        )
    started = []
    monkeypatch.setattr(background, "session_scope", lambda: session_scope(engine))
    monkeypatch.setattr(google, "get_google", lambda: object())
    monkeypatch.setattr(
        google.syncs, "start", lambda user_id, work: started.append(user_id) or True
    )
    assert background.start_due_syncs(NOON) == 1 and started == [stale]


# The API


@pytest.fixture
def client(engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "throttle", LoginThrottle())
    app = create_app()

    def db():
        with session_scope(engine) as session:
            yield session

    app.dependency_overrides[auth.get_db] = db
    app.dependency_overrides[auth.now] = lambda: NOON
    return TestClient(app)


def signed_in(client, engine, email="person@example.com") -> dict:
    token = client.post("/auth/signup", json={"email": email, "password": PASSWORD}).json()["token"]
    with session_scope(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        user.status, user.timezone = "approved", "Asia/Beirut"
        db.add(GoogleConnection(user_id=user.id, encrypted_token=b"x", status="active"))
        save_daily(db, user.id, "google_health", bad_night_frame())
    return {"Authorization": f"Bearer {token}"}


def test_the_api_lists_sent_alarms_takes_feedback_and_keeps_settings(client, engine):
    headers = signed_in(client, engine)
    other = signed_in(client, engine, "other@example.com")
    run.run_all(sessions(engine), NOON, Mailbox(), APP)
    listed = client.get("/alarms", headers=headers).json()
    assert listed and all(a["status"] == "sent" for a in listed)
    first = listed[0]
    assert first["link"].startswith("/evidence/") or first["link"] == "/settings"
    url = f"/alarms/{first['id']}/feedback"
    assert (
        client.post(url, json={"useful": False}, headers=headers).json()["feedback"] == "not_useful"
    )
    assert client.post(url, json={"useful": True}, headers=other).status_code == 404
    assert client.get("/alarm-settings", headers=headers).json() == {
        "enabled": True,
        "mutedKinds": [],
        "sensitivity": "normal",
    }
    changed = {"enabled": True, "mutedKinds": ["finding", "day"], "sensitivity": "fewer"}
    saved = client.put("/alarm-settings", json=changed, headers=headers).json()
    assert saved == {"enabled": True, "mutedKinds": ["day", "finding"], "sensitivity": "fewer"}
    bad = client.put("/alarm-settings", json={**changed, "sensitivity": "loud"}, headers=headers)
    assert bad.status_code == 422


def test_every_kind_of_alarm_has_text_from_its_own_evidence():
    """A finding compares two windows, so it has means and no usual range (seen on 2026-10-28)."""
    from app.alarms.detect import Candidate, detect, detect_finding
    from app.synthetic import Trend

    drop = Trend("hrv_ms", LAST - timedelta(days=13), LAST, -20)
    findings = []
    for seed in range(10):
        findings += detect_finding(with_scores(generate(START, 90, (drop,), seed=seed).frame), LAST)
    hrv = [c for c in findings if c.metric == "hrv_ms"]  # the recovery score drops with it
    assert hrv, "a planted two-week HRV drop should give at least one finding"
    title, body = run.text(hrv[0])
    assert title == "Heart rate variability (HRV) has dropped over two weeks"
    assert body.startswith("The last 14 days averaged ")
    kinds = {c.kind for c in detect(with_scores(bad_night_frame()), LAST)} | {"finding"}
    for candidate in [*findings, *detect(with_scores(bad_night_frame()), LAST)]:
        assert all(run.text(candidate))
    for metric in ("reconnect", "stale"):
        assert all(run.text(Candidate("data", metric, LAST, None, 1.0)))
    assert "finding" in kinds


# The agent's explanation


def test_the_owning_expert_explains_an_alarm_and_the_inbox_asks_for_feedback(client, engine):
    from app.agent.agent import SUBMIT
    from app.agent.llm import ScriptedLLM

    headers = signed_in(client, engine)
    explanation = "Last night's time asleep sat well under your usual range."
    llm = ScriptedLLM([ScriptedLLM.call(SUBMIT, summary=explanation, claims=[], cost_usd=0.004)])
    run.run_all(sessions(engine), NOON, Mailbox(), APP, llm=llm)
    with session_scope(engine) as db:
        alarm = db.scalar(select(Alarm).where(Alarm.key == "day:sleep_minutes"))
        assert alarm.body == explanation and alarm.written_by == "sleep"
        assert alarm.cost_usd == pytest.approx(0.004)
    # The expert was given the alarm and its evidence, and was told not to advise.
    task = llm.requests[0]["messages"][0]["content"]
    assert "You are the sleep expert" in task
    inbox = client.get("/notifications", headers=headers).json()["items"]
    item = next(i for i in inbox if i["title"] == "Time asleep well below your usual")
    assert item["body"] == explanation and item["alarmId"] and item["alarmFeedback"] is None
    client.post(f"/alarms/{item['alarmId']}/feedback", json={"useful": True}, headers=headers)
    again = client.get("/notifications", headers=headers).json()["items"]
    assert next(i for i in again if i["id"] == item["id"])["alarmFeedback"] == "useful"


def test_a_failed_or_unsafe_explanation_keeps_the_template(engine):
    from app.agent.agent import SUBMIT
    from app.agent.llm import LLMError, ScriptedLLM
    from app.alarms.detect import detect
    from app.alarms.explain import explain

    frame = with_scores(bad_night_frame())
    candidate = next(c for c in detect(frame, LAST) if c.metric == "sleep_minutes")
    title, body = run.text(candidate)

    def explained(llm):
        return explain(
            llm,
            frame,
            kind=candidate.kind,
            metric=candidate.metric,
            title=title,
            body=body,
            evidence=candidate.evidence,
            today=LAST,
        )

    class Down:
        def complete(self, *args, **kwargs):
            raise LLMError("OpenAI is down")

    # A metric no evidence covers ("bedtime") fails the summary check: the template stays.
    unsupported = ScriptedLLM(
        [ScriptedLLM.call(SUBMIT, summary="Shorter than usual, after a later bedtime.", claims=[])]
        * 2
    )
    assert explained(unsupported).written_by == "template"
    assert explained(Down()).written_by == "template"
    assert explained(None).body == body
    diagnosis = ScriptedLLM(
        [ScriptedLLM.call(SUBMIT, summary="This could be insomnia.", claims=[])]
    )
    assert explained(diagnosis).written_by == "template"
    nothing = ScriptedLLM([ScriptedLLM.say("I will not submit.")] * 3)
    assert explained(nothing).body == body
    # Data alarms are not sent to the model at all.
    unused = ScriptedLLM([])
    assert (
        explain(
            unused, frame, kind="data", metric="stale", title="t", body="b", evidence=[], today=LAST
        ).body
        == "b"
    )
    assert unused.requests == []
