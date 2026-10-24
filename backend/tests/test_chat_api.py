import json
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.agent.agent import SUBMIT
from app.agent.llm import Completion, ScriptedLLM, ToolCall, Usage
from app.agent.router import EXPERT_LABELS, LABELS, Classification
from app.api import auth, chat
from app.api.chat import AgentParts, answer_text
from app.api.main import create_app
from app.api.store import analyze, get_data
from app.auth.accounts import LoginThrottle
from app.config import settings
from app.db.models import ChatMessage, EvidenceRecord, MemoryFact, User
from app.db.session import session_scope
from app.ingest.takeout import DailyData
from app.synthetic import generate

START = date(2026, 7, 1)
PASSWORD = "correct horse battery"


class FixedRouter:
    def __init__(self, **given: float):
        topic = dict.fromkeys(LABELS, 0.0) | given
        self.result = Classification(topic, dict.fromkeys(EXPERT_LABELS, 0.0), source="test")

    def classify(self, question: str, earlier=()) -> Classification:
        return self.result


def submission(summary: str, cost: float = 0.0, claims=()) -> Completion:
    call = ToolCall("submit", SUBMIT, {"summary": summary, "claims": list(claims)})
    return Completion(None, (call,), "scripted", Usage(), cost, 0.0)


def describe_then_claim(text: str, cost: float = 0.004):
    """Runs `describe` on sleep, then submits one claim citing it."""

    def submit(messages):
        payload = next(
            json.loads(m["content"])
            for m in reversed(messages)
            if m["role"] == "tool" and '"tool": "describe"' in m["content"]
        )
        claim = {
            "text": text,
            "kind": "no_change",
            "evidence_ids": [payload["evidence_id"]],
            "metric": "sleep_minutes",
        }
        return submission("Here is what I found.", cost, [claim])

    end = (START + timedelta(days=59)).isoformat()
    return [
        ScriptedLLM.call("describe", metric="sleep_minutes", start=START.isoformat(), end=end),
        submit,
    ]


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


@pytest.fixture
def agent():
    return AgentParts(ScriptedLLM([]), FixedRouter(sleep=0.9), None)


@pytest.fixture
def client(engine, agent, monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "throttle", LoginThrottle())
    monkeypatch.setattr(chat, "_busy", set())
    app = create_app()

    def db():
        with session_scope(engine) as session:
            yield session

    data = analyze(DailyData(frame=generate(START, 60, seed=5).frame), datetime.now(UTC))
    app.dependency_overrides[auth.get_db] = db
    app.dependency_overrides[get_data] = lambda: data
    app.dependency_overrides[chat.get_agent] = lambda: agent
    app.dependency_overrides[chat.get_sessions] = lambda: lambda: session_scope(engine)
    return TestClient(app)


def signed_in(client, engine, email: str = "person@example.com", approved: bool = True) -> dict:
    token = client.post("/auth/signup", json={"email": email, "password": PASSWORD}).json()["token"]
    if approved:
        with session_scope(engine) as session:
            session.scalar(select(User).where(User.email == email)).status = "approved"
    return {"Authorization": f"Bearer {token}"}


def ask(client, headers, text: str = "How did I sleep?", **options):
    return client.post("/chat", json={"text": text, **options}, headers=headers)


# Access


def test_the_chat_needs_an_approved_account(client, engine):
    assert client.get("/chat").status_code == 401
    pending = signed_in(client, engine, approved=False)
    assert client.get("/chat", headers=pending).json()["error"]["code"] == "not_approved"
    assert ask(client, pending).status_code == 403


def test_a_new_person_has_an_empty_chat(client, engine):
    assert client.get("/chat", headers=signed_in(client, engine)).json() == []


# Answering


def test_a_question_is_answered_with_verified_claims_and_stored(client, engine, agent):
    agent.llm.turns.extend(describe_then_claim("Your time asleep held steady."))
    headers = signed_in(client, engine)

    response = ask(client, headers)
    assert response.status_code == 200, response.text
    question, answer = response.json()
    assert question["role"] == "user" and question["text"] == "How did I sleep?"
    assert answer["role"] == "assistant"
    # The summary is the answer; the claim backs it as evidence, not as repeated text.
    assert answer["text"] == "Here is what I found."
    assert answer["answeredBy"] == "sleep" and answer["routed"] is True
    assert len(answer["evidenceIds"]) == 1
    assert "refused" not in answer  # absent rather than false, like the mock

    assert client.get("/chat", headers=headers).json() == [question, answer]
    evidence = client.get(f"/evidence/{answer['evidenceIds'][0]}", headers=headers)
    assert evidence.status_code == 200 and evidence.json()["tool"] == "describe"
    with session_scope(engine) as session:
        assert session.scalar(select(ChatMessage.cost_usd).where(ChatMessage.role == "assistant"))
        assert session.scalar(select(EvidenceRecord.id)) == answer["evidenceIds"][0]


def test_picking_an_expert_is_not_routed(client, engine, agent):
    agent.llm.turns.append(submission("Nothing stood out."))
    answer = ask(client, signed_in(client, engine), expert="sleep", depth="deep").json()[1]
    assert answer["answeredBy"] == "sleep" and answer["routed"] is False


def test_an_out_of_scope_question_is_refused_at_no_cost(client, engine, agent):
    agent.router.result = Classification(
        dict.fromkeys(LABELS, 0.0) | {"out_of_scope": 0.95},
        dict.fromkeys(EXPERT_LABELS, 0.0),
        source="test",
    )
    answer = ask(client, signed_in(client, engine), "Do I have apnea?").json()[1]
    assert answer["refused"] is True
    assert "answeredBy" not in answer and agent.llm.requests == []


def test_earlier_turns_are_given_to_the_next_answer(client, engine, agent):
    headers = signed_in(client, engine)
    agent.llm.turns.append(submission("Nothing stood out."))
    ask(client, headers, "How did I sleep last month?")
    agent.llm.turns.append(submission("Weekends looked the same."))
    ask(client, headers, "What about on weekends?")
    second_run = json.dumps(agent.llm.requests[-1]["messages"])
    assert "How did I sleep last month?" in second_run
    assert len(client.get("/chat", headers=headers).json()) == 4


def test_people_never_see_each_others_chat(client, engine, agent):
    first = signed_in(client, engine, "first@example.com")
    second = signed_in(client, engine, "second@example.com")
    agent.llm.turns.append(submission("Nothing stood out."))
    ask(client, first, "A question only I asked")
    assert client.get("/chat", headers=second).json() == []
    agent.llm.turns.append(submission("Nothing stood out."))
    ask(client, second)
    assert "A question only I asked" not in json.dumps(agent.llm.requests[-1]["messages"])


def test_a_proposed_fact_waits_for_approval(client, engine, agent):
    propose = ScriptedLLM.call(
        "propose_fact", kind="routine", text="Works night shifts since August"
    )
    agent.llm.turns.extend([propose, submission("Nothing stood out.")])
    ask(client, signed_in(client, engine), "I work night shifts since August. How is my sleep?")
    with session_scope(engine) as session:
        fact = session.scalar(select(MemoryFact))
        assert fact.text == "Works night shifts since August" and fact.status == "proposed"


def test_a_failed_run_is_stored_as_a_plain_apology(client, engine, agent):
    # The script is empty, so the model call fails.
    question, answer = ask(client, signed_in(client, engine)).json()
    assert answer["text"] == chat.FAILED
    assert question["text"] == "How did I sleep?"


def test_the_answer_text_is_the_summary_then_the_notes():
    text = answer_text("Your sleep held steady.", ["A.", "B."], ["Note."])
    assert text == "Your sleep held steady.\n\nNote."
    # Without a summary, the claims are read out as one paragraph, capitalized.
    assert answer_text("", ["time asleep held steady.", "Bedtime too."], []) == (
        "Time asleep held steady. Bedtime too."
    )
    assert answer_text("", [], []) == chat.FAILED


def test_the_agent_gets_the_local_time_not_the_last_day_of_data(client, engine, agent):
    agent.llm.turns.append(submission("Nothing stood out."))
    ask(client, signed_in(client, engine))
    task = agent.llm.requests[0]["messages"][1]["content"]
    assert task.startswith("It is now ") and "UTC" in task


def test_a_reply_to_a_logging_question_is_given_with_its_request(client, engine, agent):
    from app.agent.intent import Intent

    headers = signed_in(client, engine)
    # The agent asks for the time instead of preparing a draft.
    agent.router.result = Classification(
        dict.fromkeys(LABELS, 0.0) | {"nutrition": 0.95},
        dict.fromkeys(EXPERT_LABELS, 0.0),
        source="test",
        intent_probabilities={str(i): float(i == Intent.LOG) for i in Intent},
    )
    agent.llm.turns.append(submission("When did you eat it?"))
    ask(client, headers, "Log a snack: an apple, 95 kcal")
    # The reply alone is unclear; it continues the logging request.
    agent.router.result = Classification(
        dict.fromkeys(LABELS, 0.0) | {"nutrition": 0.95},
        dict.fromkeys(EXPERT_LABELS, 0.0),
        source="test",
        intent_probabilities={str(i): float(i == Intent.CLARIFY) for i in Intent},
    )
    agent.llm.turns.append(submission("Noted."))
    ask(client, headers, "at 10:30")
    task = agent.llm.requests[-1]["messages"][1]["content"]
    assert "Earlier request: Log a snack: an apple, 95 kcal" in task
    assert "You asked: When did you eat it?" in task
    assert "Their reply: at 10:30" in task
    # What is stored and shown stays the person's own words.
    assert client.get("/chat", headers=headers).json()[-2]["text"] == "at 10:30"


# Attachments


def test_an_attached_metric_leads_and_an_unknown_one_is_refused(client, engine, agent):
    headers = signed_in(client, engine)
    agent.llm.turns.append(submission("Nothing stood out."))
    attachment = {"kind": "metric", "metric": "steps"}
    question, answer = ask(client, headers, "What about this?", attachment=attachment).json()
    assert question["attachment"] == attachment
    assert answer["answeredBy"] == "activity"
    bad = ask(client, headers, attachment={"kind": "metric", "metric": "made_up"})
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "attachment", [{"kind": "finding"}, {"kind": "metric"}, {"kind": "other", "id": "x"}]
)
def test_incomplete_attachments_are_invalid(client, engine, attachment):
    response = ask(client, signed_in(client, engine), attachment=attachment)
    assert response.status_code == 422


def test_an_unknown_finding_is_not_found(client, engine):
    response = ask(client, signed_in(client, engine), attachment={"kind": "finding", "id": "f9"})
    assert response.status_code == 404


@pytest.mark.parametrize("text", ["", "x" * 2001])
def test_empty_or_huge_questions_are_invalid(client, engine, text):
    assert ask(client, signed_in(client, engine), text).status_code == 422


# Spending and waiting


def test_a_person_stops_at_their_daily_cap(client, engine, agent, monkeypatch):
    monkeypatch.setattr(settings, "chat_daily_cap_per_user_usd", 0.01)
    headers = signed_in(client, engine)
    agent.llm.turns.append(submission("Nothing stood out.", cost=0.012))
    assert ask(client, headers).status_code == 200
    refused = ask(client, headers)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "daily_limit"
    # Someone else can still ask.
    agent.llm.turns.append(submission("Nothing stood out."))
    assert ask(client, signed_in(client, engine, "other@example.com")).status_code == 200


def test_the_app_stops_at_its_daily_total(client, engine, agent, monkeypatch):
    monkeypatch.setattr(settings, "chat_daily_cap_total_usd", 0.01)
    agent.llm.turns.append(submission("Nothing stood out.", cost=0.012))
    assert ask(client, signed_in(client, engine, "first@example.com")).status_code == 200
    refused = ask(client, signed_in(client, engine, "second@example.com"))
    assert refused.json()["error"]["code"] == "app_daily_limit"


def test_yesterdays_spending_does_not_count(client, engine, agent, monkeypatch):
    monkeypatch.setattr(settings, "chat_daily_cap_per_user_usd", 0.01)
    headers = signed_in(client, engine)
    agent.llm.turns.append(submission("Nothing stood out.", cost=0.012))
    ask(client, headers)
    with session_scope(engine) as session:
        for message in session.scalars(select(ChatMessage)):
            message.created_at -= timedelta(days=2)
    agent.llm.turns.append(submission("Nothing stood out."))
    assert ask(client, headers).status_code == 200


def test_a_slow_answer_is_stored_when_it_is_ready(client, engine, agent, monkeypatch):
    monkeypatch.setattr(settings, "chat_wait_s", 0.05)
    headers = signed_in(client, engine)

    def slow(messages):
        time.sleep(0.3)
        return submission("Nothing stood out.")

    agent.llm.turns.append(slow)
    response = ask(client, headers)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "still_answering"
    busy = ask(client, headers)  # the first is still running
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "busy"

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and len(client.get("/chat", headers=headers).json()) < 2:
        time.sleep(0.05)
    messages = client.get("/chat", headers=headers).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["text"].startswith("Nothing stood out.")
