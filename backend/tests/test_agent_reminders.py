import json
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select

from app.agent.intent import Intent, keyword_intent
from app.db.models import Reminder, User
from app.db.session import session_scope
from app.reminders.tools import REMINDER_NOTE, reminder_reply, reminder_tools

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
NIGHTS = {"kind": "weekly", "time": "22:30", "weekdays": [0, 1, 2, 3, 4]}


@pytest.mark.parametrize(
    "text",
    [
        "Remind me every weeknight at 22:30 to wind down",
        "can you set a reminder to drink water at 3pm",
        "stop reminding me about stretching",
        "What reminders do I have?",
    ],
)
def test_reminder_requests_have_their_own_intent(text):
    probabilities = keyword_intent(text)
    assert max(probabilities, key=probabilities.get) == Intent.REMIND


def test_logging_and_questions_keep_their_intents():
    def top(text):
        probabilities = keyword_intent(text)
        return max(probabilities, key=probabilities.get)

    assert top("Log lunch with 40 g protein") == Intent.LOG
    assert top("How did I sleep?") == Intent.READ


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    with session_scope(engine) as db:
        db.add(User(email="person@example.com", status="approved", timezone="Asia/Beirut"))
    return engine


def tools(engine, prepared):
    with session_scope(engine) as db:
        user_id = db.scalar(select(User)).id
    propose, listing = reminder_tools(lambda: session_scope(engine), user_id, NOW, prepared)
    return propose, listing


def test_a_proposed_reminder_waits_for_the_persons_tap(engine):
    prepared = []
    propose, listing = tools(engine, prepared)
    content, step = propose.run(
        {"title": "Wind down", "message": "Screens off soon.", "schedule": NIGHTS}
    )
    answer = json.loads(content)
    assert answer["status"] == "proposed" and answer["schedule"] == "Weeknights at 22:30"
    assert prepared == [answer["reminder_id"]] == [step["reminder_id"]]
    with session_scope(engine) as db:
        row = db.scalar(select(Reminder))
        assert row.status == "proposed" and row.next_due_at is None and row.source == "agent"
        assert row.channels == ["email", "in_app"]
    listed = json.loads(listing.run({})[0])["reminders"]
    assert listed == [
        {
            "title": "Wind down",
            "schedule": "Weeknights at 22:30",
            "status": "proposed",
            "channels": ["email", "in_app"],
        }
    ]


@pytest.mark.parametrize(
    "arguments, error",
    [
        ({"title": "Take my pills", "message": "", "schedule": NIGHTS}, "medical"),
        ({"title": "Insulin", "message": "dose", "schedule": NIGHTS}, "medical"),
        (
            {"title": "Water", "message": "", "schedule": {"kind": "weekly", "time": "25:00"}},
            "invalid_reminder",
        ),
        (
            {
                "title": "Water",
                "message": "",
                "schedule": {"kind": "once", "date": "2026-10-27", "time": "08:00"},
            },
            "in_the_past",
        ),
        ({"title": "", "message": "", "schedule": NIGHTS}, "invalid_reminder"),
    ],
)
def test_bad_reminders_are_refused_with_a_reason_the_model_can_use(engine, arguments, error):
    prepared = []
    propose, _ = tools(engine, prepared)
    content, step = propose.run(arguments)
    assert step == {"error": error} and "error" in json.loads(content)
    assert prepared == []


def test_at_most_three_reminders_in_one_answer(engine):
    prepared = []
    propose, _ = tools(engine, prepared)
    for title in ("One", "Two", "Three", "Four"):
        propose.run({"title": title, "message": "", "schedule": NIGHTS})
    assert len(prepared) == 3


@pytest.mark.parametrize(
    "summary, kept",
    [
        ("Here's your wind-down reminder. Tap Set on the card to turn it on.", True),
        ("Nice idea! Check the card and tap Set when you're happy with it.", True),
        ("I've set your reminder for weeknights.", False),
        ("Done! Your reminder is scheduled.", False),
        ("Here is your reminder.", False),  # does not say it waits for a tap
        ("", False),
    ],
)
def test_a_reply_may_not_claim_the_reminder_is_on(summary, kept):
    assert reminder_reply(summary) == (summary.strip() if kept else REMINDER_NOTE)
