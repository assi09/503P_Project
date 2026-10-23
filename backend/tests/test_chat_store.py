import uuid
from datetime import date, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.analysis import tools
from app.analysis.evidence import Window
from app.db.chat import add_answer, add_question, history, load_evidence
from app.db.models import ChatMessage, EvidenceRecord, User
from app.synthetic import generate

START = date(2026, 7, 1)
WINDOW = Window(start=START, end=START + timedelta(59))


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    # SQLite enforces ON DELETE CASCADE only with foreign keys switched on.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        with Session(bind=connection) as session:
            yield session


@pytest.fixture(scope="module")
def evidence():
    frame = generate(START, 60, seed=2).frame
    return [
        tools.describe(frame, "sleep_minutes", WINDOW),
        tools.correlate(frame, "bedtime_hour", "sleep_minutes", WINDOW, 2),
        tools.coverage(frame, WINDOW),
    ]


def person(session: Session, email: str = "person@example.com") -> uuid.UUID:
    user = User(email=email)
    session.add(user)
    session.flush()
    return user.id


def claim(*evidence) -> dict:
    return {
        "text": "Your time asleep held steady.",
        "kind": "no_change",
        "evidence_ids": [e.id for e in evidence],
        "metric": "sleep_minutes",
    }


def answer(session, user_id, evidence, claims, **fields):
    defaults = {
        "answered_by": "sleep",
        "routed": True,
        "consulted": [],
        "refused": False,
        "run_id": "run1",
    }
    return add_answer(
        session,
        user_id,
        "Here is what I found.",
        claims=claims,
        evidence=evidence,
        **defaults | fields,
    )


def test_a_turn_round_trips_with_its_claims_and_cited_evidence(session, evidence):
    user_id = person(session)
    add_question(
        session, user_id, "How is my sleep?", {"kind": "metric", "metric": "sleep_minutes"}
    )
    stored = answer(session, user_id, evidence, [claim(evidence[0], evidence[1])])
    turns = history(session, user_id)
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].attachment == {"kind": "metric", "metric": "sleep_minutes"}
    assert turns[1].claims == [claim(evidence[0], evidence[1])]
    assert stored.evidence_ids == sorted([evidence[0].id, evidence[1].id])
    loaded = load_evidence(session, user_id, stored.evidence_ids)
    assert loaded == {e.id: e for e in evidence[:2]}  # identical to what the tools returned


def test_only_cited_evidence_is_kept(session, evidence):
    user_id = person(session)
    answer(session, user_id, evidence, [claim(evidence[0])])
    kept = session.scalars(select(EvidenceRecord.id)).all()
    assert kept == [evidence[0].id]  # the correlation and coverage were not cited


def test_evidence_cited_again_is_stored_once(session, evidence):
    user_id = person(session)
    answer(session, user_id, evidence, [claim(evidence[0])])
    answer(session, user_id, evidence, [claim(evidence[0])], run_id="run2")
    assert len(session.scalars(select(EvidenceRecord)).all()) == 1


def test_an_answer_cannot_cite_evidence_it_does_not_bring(session, evidence):
    user_id = person(session)
    with pytest.raises(ValueError, match="not given"):
        answer(session, user_id, evidence[1:], [claim(evidence[0])])


def test_a_refusal_is_stored_without_claims(session, evidence):
    user_id = person(session)
    add_question(session, user_id, "Do I have apnea?")
    stored = answer(session, user_id, [], [], answered_by=None, routed=None, refused=True)
    assert stored.refused and stored.claims == [] and stored.evidence_ids == []


def test_history_is_oldest_first_and_can_be_limited(session, evidence):
    user_id = person(session)
    for n in range(3):
        add_question(session, user_id, f"Question {n}?")
        answer(session, user_id, evidence, [])
    assert [t.text for t in history(session, user_id)][::2] == [
        "Question 0?",
        "Question 1?",
        "Question 2?",
    ]
    latest = history(session, user_id, limit=2)
    assert [t.role for t in latest] == ["user", "assistant"] and latest[0].text == "Question 2?"


def test_one_persons_conversation_and_evidence_are_invisible_to_another(session, evidence):
    owner, other = person(session), person(session, "other@example.com")
    add_question(session, owner, "How is my sleep?")
    stored = answer(session, owner, evidence, [claim(evidence[0])])
    assert history(session, other) == []
    assert load_evidence(session, other, stored.evidence_ids) == {}


def test_deleting_a_person_deletes_their_conversation_and_evidence(session, evidence):
    user_id = person(session)
    add_question(session, user_id, "How is my sleep?")
    answer(session, user_id, evidence, [claim(evidence[0])])
    session.execute(delete(User).where(User.id == user_id))
    assert session.scalars(select(ChatMessage)).all() == []
    assert session.scalars(select(EvidenceRecord)).all() == []
