from datetime import date

import pytest

from app.agent.agent import SUBMIT
from app.agent.ask import REFUSAL, ask, default_router
from app.agent.experts import CONSULT
from app.agent.llm import Completion, ScriptedLLM, ToolCall, Usage
from app.agent.router import (
    EXPERT_LABELS,
    LABELS,
    Classification,
    FallbackRouter,
    KeywordRouter,
    RouterError,
)
from app.config import Settings
from app.synthetic import generate


@pytest.fixture(scope="module")
def frame():
    return generate(date(2026, 7, 1), 60, seed=5).frame


class FixedRouter:
    def __init__(self, needs: tuple[str, ...] = (), **given: float):
        topic = dict.fromkeys(LABELS, 0.0) | given
        needed = {e: 1.0 if e in needs else 0.0 for e in EXPERT_LABELS}
        self.result = Classification(topic, needed, source="test")
        self.questions: list[str] = []
        self.earlier: list[list[str]] = []

    def classify(self, question: str, earlier=()) -> Classification:
        self.questions.append(question)
        self.earlier.append(list(earlier))
        return self.result


def route_step(reply) -> dict:
    return next(s for s in reply.result.trace if s["type"] == "route")


def empty_submission() -> Completion:
    call = ToolCall("submit", SUBMIT, {"summary": "Nothing stood out.", "claims": []})
    return Completion(None, (call,), "scripted", Usage(), 0.0, 0.0)


def test_an_out_of_scope_question_is_refused_without_calling_the_model(frame):
    llm = ScriptedLLM([])
    reply = ask(llm, FixedRouter(out_of_scope=0.9, sleep=0.1), frame, "Do I have apnea?")
    assert reply.result.stop_reason == "refused" and reply.result.summary == REFUSAL
    assert llm.requests == []
    assert [s["type"] for s in reply.result.trace] == ["context", "route"]
    assert route_step(reply)["action"] == "refuse"


def test_a_clear_question_goes_to_its_expert_without_consults(frame):
    llm = ScriptedLLM([empty_submission()])
    reply = ask(llm, FixedRouter(sleep=0.9, general=0.1), frame, "How is my sleep?")
    assert reply.result.expert == "sleep" and reply.route.routed
    assert "You are the sleep expert" in llm.requests[0]["messages"][0]["content"]
    assert CONSULT not in llm.requests[0]["tools"]


def test_a_cross_domain_question_lets_the_lead_consult_the_other_expert(frame):
    llm = ScriptedLLM([empty_submission()])
    router = FixedRouter(("recovery", "sleep"), recovery=0.75, sleep=0.25)
    reply = ask(llm, router, frame, "Did my late nights hurt my recovery?")
    assert reply.result.expert == "recovery" and reply.route.consult == ("sleep",)
    assert CONSULT in llm.requests[0]["tools"]
    step = route_step(reply)
    assert step["expert"] == "recovery" and step["consult"] == ["sleep"]
    assert step["probabilities"]["sleep"] == pytest.approx(0.25)
    assert step["needs"] == {"sleep": 1.0, "recovery": 1.0, "activity": 0.0, "nutrition": 0.0}


def test_low_confidence_goes_to_the_general_agent(frame):
    llm = ScriptedLLM([empty_submission()])
    reply = ask(llm, FixedRouter(sleep=0.34, recovery=0.33, activity=0.33), frame, "Anything?")
    assert reply.route.action == "general" and reply.result.expert == "general"
    assert "You are the" not in llm.requests[0]["messages"][0]["content"]


def test_a_chosen_expert_answers_and_the_answer_says_it_was_chosen(frame):
    llm = ScriptedLLM([empty_submission()])
    router = FixedRouter(("sleep",), sleep=1.0)
    reply = ask(llm, router, frame, "How is my sleep?", choice="activity")
    assert reply.result.expert == "activity" and not reply.route.routed
    assert reply.route.consult == ("sleep",)  # the router still decides who is consulted


def test_only_the_question_reaches_the_router(frame):
    router = FixedRouter(sleep=1.0)
    ask(ScriptedLLM([empty_submission()]), router, frame, "How is my sleep?")
    assert router.questions == ["How is my sleep?"]


def test_without_a_typesafe_key_the_keyword_rule_routes():
    assert isinstance(default_router(Settings(typesafe_api_key=None)), KeywordRouter)
    router = default_router(Settings(typesafe_api_key="key"))
    assert isinstance(router, FallbackRouter) and isinstance(router.fallback, KeywordRouter)
    assert issubclass(RouterError, RuntimeError)


def submit_claims(claims: list[dict]) -> Completion:
    call = ToolCall("submit", SUBMIT, {"summary": "Here is what I found.", "claims": claims})
    return Completion(None, (call,), "scripted", Usage(), 0.0, 0.0)


@pytest.fixture(scope="module")
def sleep_evidence(frame):
    from app.analysis import tools
    from app.analysis.evidence import Window

    window = Window(start=date(2026, 7, 1), end=date(2026, 8, 29))
    return tools.describe(frame, "sleep_minutes", window)


def earlier_sleep_turn(evidence, answered_by="sleep"):
    from app.agent.context import Turn

    claim = {
        "text": "Your time asleep held steady.",
        "kind": "no_change",
        "evidence_ids": [evidence.id],
        "metric": "sleep_minutes",
    }
    return Turn("How is my sleep?", "Your time asleep held steady.", (claim,), answered_by)


def steady_sleep_claim(evidence) -> dict:
    return {
        "text": "Your time asleep held steady.",
        "kind": "no_change",
        "evidence_ids": [evidence.id],
        "metric": "sleep_minutes",
    }


def test_a_follow_up_is_routed_with_earlier_questions_and_sees_the_conversation(
    frame, sleep_evidence
):
    llm = ScriptedLLM([empty_submission()])
    router = FixedRouter(("sleep",), sleep=0.9, general=0.1)
    history = [earlier_sleep_turn(sleep_evidence)]
    reply = ask(
        llm,
        router,
        frame,
        "And last week?",
        history=history,
        stored_evidence={sleep_evidence.id: sleep_evidence},
    )
    assert router.earlier == [["How is my sleep?"]]
    task = llm.requests[0]["messages"][1]["content"]
    assert "<context>" in task and "How is my sleep?" in task
    assert task.index("<context>") < task.index("The person asks: And last week?")
    step = reply.result.trace[0]
    assert step["type"] == "context" and step["turns_verbatim"] == [0]
    assert step["evidence"] == [sleep_evidence.id]


def test_a_follow_up_may_cite_an_earlier_answers_evidence_without_recomputing(
    frame, sleep_evidence
):
    llm = ScriptedLLM([submit_claims([steady_sleep_claim(sleep_evidence)])])
    reply = ask(
        llm,
        FixedRouter(("sleep",), sleep=1.0),
        frame,
        "Is that still true?",
        history=[earlier_sleep_turn(sleep_evidence)],
        stored_evidence={sleep_evidence.id: sleep_evidence},
    )
    assert len(reply.result.claims) == 1 and reply.result.rejected == []
    assert not [s for s in reply.result.trace if s["type"] == "tool"]  # nothing recomputed


def test_earlier_evidence_counts_as_its_owners_for_another_lead(frame, sleep_evidence):
    # Recovery may claim about sleep on the sleep expert's earlier evidence, not on the general
    # agent's.
    def run(answered_by):
        llm = ScriptedLLM([submit_claims([steady_sleep_claim(sleep_evidence)])] * 2)
        return ask(
            llm,
            FixedRouter(("recovery",), recovery=1.0),
            frame,
            "Did that go with my HRV?",
            history=[earlier_sleep_turn(sleep_evidence, answered_by)],
            stored_evidence={sleep_evidence.id: sleep_evidence},
        ).result

    assert len(run("sleep").claims) == 1
    assert run("general").claims == []


def test_an_attached_metric_decides_the_lead_unless_the_person_picked_one(frame):
    from app.agent.context import Attachment

    router = FixedRouter(("sleep",), sleep=1.0)
    attached = Attachment("hrv_ms")
    reply = ask(ScriptedLLM([empty_submission()]), router, frame, "Why?", attachment=attached)
    assert reply.result.expert == "recovery" and not reply.route.routed
    assert reply.route.consult == ("sleep",)  # the router still decides who is consulted
    picked = ask(
        ScriptedLLM([empty_submission()]),
        router,
        frame,
        "Why?",
        attachment=attached,
        choice="activity",
    )
    assert picked.result.expert == "activity"


def test_an_attachment_does_not_get_a_medical_question_answered(frame):
    from app.agent.context import Attachment

    llm = ScriptedLLM([])
    router = FixedRouter(out_of_scope=0.9, recovery=0.1)
    reply = ask(llm, router, frame, "Is this arrhythmia?", attachment=Attachment("hrv_ms"))
    assert reply.result.stop_reason == "refused" and llm.requests == []
