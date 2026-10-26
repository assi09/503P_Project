"""Team report emails: what they hold, what they never hold, and how they are delivered."""

import json
from datetime import UTC, date, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import create_engine, select

from app.analysis.team import week_of
from app.db.daily import save_daily
from app.db.models import Base, Team, TeamReport, User
from app.db.session import session_scope
from app.synthetic import Step, generate
from app.teams import memberships, reports
from app.teams.email import (
    RESEND_URL,
    Email,
    MailError,
    OutboxMailer,
    ResendMailer,
    compose,
    deliver,
    mailer_from_settings,
)

NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
WEEK = week_of(date(2026, 10, 19))
APP = "https://app.example.com"


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def made_report(engine, size=6, sharing=(0, 1), report_email=None):
    start = WEEK.start - timedelta(days=80)
    drop = (Step("sleep_minutes", WEEK.start, -70),)
    with session_scope(engine) as db:
        boss = User(email="boss@example.com", status="approved", role="supervisor")
        db.add(boss)
        db.flush()
        team = memberships.create_team(db, boss, "Design", report_email, NOW)
        for i in range(size):
            person = User(email=f"member{i:02d}@example.com", status="approved")
            db.add(person)
            db.flush()
            save_daily(db, person.id, "google_health", generate(start, 87, drop, seed=i).frame)
            memberships.join(db, team, person, NOW)
            if i in sharing:
                memberships.share_levels(db, person, str(team.id), True, NOW)
        reports.build_report(db, team, WEEK, NOW)
        return team.id


class Box:
    def __init__(self):
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)


def test_an_email_holds_the_headline_counts_and_a_link_and_nobody_in_particular(engine):
    team_id = made_report(engine, sharing=(0, 1, 2))
    with session_scope(engine) as db:
        team = db.get(Team, team_id)
        report = db.scalar(select(TeamReport))
        email = compose(team, report, "boss@example.com", APP)
    assert email.subject == "Design: week of Oct 19 – Oct 25"
    for body in (email.text, email.html):
        assert "Time asleep" in body and f"{APP}/team" in body
        assert "6 people with data" in body
        # Named levels and members stay in the app, even for people who share them.
        assert "member0" not in body and "@example.com" not in body
    assert report.headline in email.text
    assert "higher of 6)" in email.text  # how many went each way, never who


def test_a_withheld_report_is_emailed_without_figures(engine):
    team_id = made_report(engine, size=3, sharing=())
    with session_scope(engine) as db:
        email = compose(db.get(Team, team_id), db.scalar(select(TeamReport)), "b@example.com", APP)
    assert "3 of the 5 people needed" in email.text
    assert "higher of" not in email.text and "People lower" not in email.html


def test_a_report_is_emailed_once_to_the_report_address_or_the_supervisor(engine):
    team_id = made_report(engine)
    box = Box()
    with session_scope(engine) as db:
        team, report = db.get(Team, team_id), db.scalar(select(TeamReport))
        assert deliver(db, team, report, box, APP, NOW) is True
        assert deliver(db, team, report, box, APP, NOW) is False
        assert report.emailed_at is not None
    assert [e.to for e in box.sent] == ["boss@example.com"]

    other = create_engine("sqlite://")
    Base.metadata.create_all(other)
    team_id = made_report(other, report_email="reports@example.com")
    with session_scope(other) as db:
        deliver(db, db.get(Team, team_id), db.scalar(select(TeamReport)), box, APP, NOW)
    assert box.sent[-1].to == "reports@example.com"


def test_the_outbox_writes_files_to_open(tmp_path):
    OutboxMailer(tmp_path).send(Email("a@example.com", "Design: week of Oct 19", "hi", "<p>hi</p>"))
    assert (tmp_path / "design-week-of-oct-19.html").read_text() == "<p>hi</p>"
    assert "To: a@example.com" in (tmp_path / "design-week-of-oct-19.txt").read_text()


def test_resend_gets_one_request_with_the_key_as_bearer():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx2.Response(200, json={"id": "made-up"})

    mailer = ResendMailer(
        "re_test",
        "Patterns <x@example.com>",
        httpx2.Client(transport=httpx2.MockTransport(respond)),
    )
    mailer.send(Email("a@example.com", "Subject", "text", "<p>html</p>"))
    (request,) = seen
    assert str(request.url) == RESEND_URL
    assert request.headers["authorization"] == "Bearer re_test"
    assert json.loads(request.content) == {
        "from": "Patterns <x@example.com>",
        "to": ["a@example.com"],
        "subject": "Subject",
        "html": "<p>html</p>",
        "text": "text",
    }


@pytest.mark.parametrize(
    ("respond", "message"),
    [
        (lambda r: httpx2.Response(403, json={"message": "domain not verified"}), "domain not"),
        (lambda r: httpx2.Response(500, text="oops"), "(500)"),
    ],
)
def test_resend_refusals_raise_a_printable_error_without_the_key(respond, message):
    mailer = ResendMailer(
        "re_secret", "x@example.com", httpx2.Client(transport=httpx2.MockTransport(respond))
    )
    with pytest.raises(MailError) as caught:
        mailer.send(Email("a@example.com", "s", "t", "h"))
    assert message in str(caught.value) and "re_secret" not in str(caught.value)


def test_unreachable_resend_raises_a_mail_error():
    def respond(request):
        raise httpx2.ConnectError("down")

    mailer = ResendMailer(
        "k", "x@example.com", httpx2.Client(transport=httpx2.MockTransport(respond))
    )
    with pytest.raises(MailError, match="Could not reach Resend"):
        mailer.send(Email("a@example.com", "s", "t", "h"))


def test_resend_needs_a_key(monkeypatch, tmp_path):
    from app.config import Settings

    settings = Settings(email_backend="resend", email_api_key=None, data_dir=tmp_path)
    with pytest.raises(MailError, match="FA_EMAIL_API_KEY"):
        mailer_from_settings(settings)
    assert isinstance(mailer_from_settings(Settings(data_dir=tmp_path)), OutboxMailer)
