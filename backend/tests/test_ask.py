from datetime import date

import pytest

from app.agent.agent import SUBMIT
from app.agent.ask import REFUSAL, ask, default_router
from app.agent.experts import CONSULT
from app.agent.llm import Completion, ScriptedLLM, ToolCall, Usage
from app.agent.router import LABELS, Classification, FallbackRouter, KeywordRouter, RouterError
from app.config import Settings
from app.synthetic import generate


@pytest.fixture(scope="module")
def frame():
    return generate(date(2026, 7, 1), 60, seed=5).frame


class FixedRouter:
    def __init__(self, **given: float):
        self.result = Classification(dict.fromkeys(LABELS, 0.0) | given, source="test")
        self.questions: list[str] = []

    def classify(self, question: str) -> Classification:
        self.questions.append(question)
        return self.result


def empty_submission() -> Completion:
    call = ToolCall("submit", SUBMIT, {"summary": "Nothing stood out.", "claims": []})
    return Completion(None, (call,), "scripted", Usage(), 0.0, 0.0)


def test_an_out_of_scope_question_is_refused_without_calling_the_model(frame):
    llm = ScriptedLLM([])
    reply = ask(llm, FixedRouter(out_of_scope=0.9, sleep=0.1), frame, "Do I have apnea?")
    assert reply.result.stop_reason == "refused" and reply.result.summary == REFUSAL
    assert llm.requests == []
    assert reply.result.trace[0]["type"] == "route"
    assert reply.result.trace[0]["action"] == "refuse"


def test_a_clear_question_goes_to_its_expert_without_consults(frame):
    llm = ScriptedLLM([empty_submission()])
    reply = ask(llm, FixedRouter(sleep=0.9, general=0.1), frame, "How is my sleep?")
    assert reply.result.expert == "sleep" and reply.route.routed
    assert "You are the sleep expert" in llm.requests[0]["messages"][0]["content"]
    assert CONSULT not in llm.requests[0]["tools"]


def test_a_cross_domain_question_lets_the_lead_consult_the_other_expert(frame):
    llm = ScriptedLLM([empty_submission()])
    router = FixedRouter(recovery=0.55, sleep=0.45)
    reply = ask(llm, router, frame, "Did my late nights hurt my recovery?")
    assert reply.result.expert == "recovery" and reply.route.consult == ("sleep",)
    assert CONSULT in llm.requests[0]["tools"]
    step = reply.result.trace[0]
    assert step["expert"] == "recovery" and step["consult"] == ["sleep"]
    assert step["probabilities"]["sleep"] == pytest.approx(0.45)


def test_low_confidence_goes_to_the_general_agent(frame):
    llm = ScriptedLLM([empty_submission()])
    reply = ask(llm, FixedRouter(sleep=0.34, recovery=0.33, activity=0.33), frame, "Anything?")
    assert reply.route.action == "general" and reply.result.expert == "general"
    assert "You are the" not in llm.requests[0]["messages"][0]["content"]


def test_a_chosen_expert_answers_and_the_answer_says_it_was_chosen(frame):
    llm = ScriptedLLM([empty_submission()])
    reply = ask(llm, FixedRouter(sleep=1.0), frame, "How is my sleep?", choice="activity")
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
