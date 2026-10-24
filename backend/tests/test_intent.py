import json
import math

import httpx2
import pytest

from app.agent.intent import (
    INTENT_AT,
    Intent,
    decide_intent,
    intent_probabilities,
    keyword_intent,
)
from app.agent.llm import ScriptedLLM
from app.agent.router import FallbackRouter, JevRouter, KeywordRouter, LLMRouter, RouterError


def distribution(mode, p=1.0):
    return {str(i): p if i == mode else (1 - p) / (len(Intent) - 1) for i in Intent}


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        ("How much protein did I eat yesterday?", Intent.READ),
        ("What did I log for lunch?", Intent.READ),
        ("How do I log food?", Intent.READ),
        ("Compare protein intake on workout days.", Intent.READ),
        ("Log lunch: rice and chicken.", Intent.LOG),
        ("Please record a run.", Intent.LOG),
        ("Could you log 300 ml of water?", Intent.LOG),
        ("Log lunch and show me my protein total.", Intent.MIXED),
        ("Show me yesterday's protein and log lunch.", Intent.CLARIFY),
        ("I had chicken and rice.", Intent.CLARIFY),
        ("I ran this morning.", Intent.CLARIFY),
        ("Here is a photo of lunch.", Intent.CLARIFY),
        ("I don't want you to log this meal.", Intent.CLARIFY),
        ("Don't log lunch, just tell me about my protein.", Intent.CLARIFY),
        ("Undo the last meal entry.", Intent.MANAGE),
        ("Please cancel that draft.", Intent.MANAGE),
        ("Yes, confirm it.", Intent.CLARIFY),
        ("Same as yesterday.", Intent.CLARIFY),
        ("650 kcal and 40 g protein.", Intent.CLARIFY),
        ('Food name: "log a workout"', Intent.CLARIFY),
        ("", Intent.CLARIFY),
    ],
)
def test_keyword_intent_separates_analysis_requests_from_logging(text, mode):
    assert decide_intent(keyword_intent(text)) == mode


def test_topic_and_intent_are_independent_and_old_logging_is_not_inherited():
    router = KeywordRouter()
    assert router.classify("Log a meal.").intent == Intent.LOG
    read = router.classify("How much protein did I eat?", ["Log a meal."])
    assert read.top == "nutrition" and read.intent == Intent.READ
    follow_up = router.classify("Yes.", ["Log a meal."])
    assert follow_up.top == "nutrition" and follow_up.intent == Intent.CLARIFY


def test_intent_is_not_a_scope_bypass():
    from app.agent.router import decide

    classified = KeywordRouter().classify("Log a meal and tell me if I have insomnia.")
    assert classified.intent == Intent.LOG
    assert decide(classified, choice="nutrition").action == "refuse"


def test_uncertain_or_absent_intent_needs_clarification():
    assert decide_intent({}) == Intent.CLARIFY
    assert decide_intent(distribution(Intent.LOG, INTENT_AT - 0.01)) == Intent.CLARIFY
    assert decide_intent(distribution(Intent.LOG, INTENT_AT + 0.01)) == Intent.LOG


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {"log": 1},
        distribution(Intent.LOG) | {"execute": 1},
        dict.fromkeys(Intent, 0),
        distribution(Intent.LOG) | {"log": True},
        distribution(Intent.LOG) | {"log": "1"},
        distribution(Intent.LOG) | {"log": -0.1},
        distribution(Intent.LOG) | {"log": 1.1},
        distribution(Intent.LOG) | {"log": math.nan},
        distribution(Intent.LOG) | {"log": math.inf},
    ],
)
def test_malformed_intents_are_rejected(raw):
    with pytest.raises(ValueError):
        intent_probabilities(raw)


def jev_body(intent):
    return {
        "answers": {
            "topic": {"type": "choice", "probabilities": {"nutrition": 1}},
            **{
                f"needs_{e}": {"type": "noul", "noul": 0}
                for e in ("sleep", "recovery", "activity", "nutrition")
            },
            "intent": intent,
        }
    }


def test_jev_asks_topic_and_intent_in_one_call_without_account_or_sensor_data():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(
            200, json=jev_body({"type": "choice", "probabilities": distribution(Intent.MIXED)})
        )

    router = JevRouter("fake-key", http=httpx2.Client(transport=httpx2.MockTransport(respond)))
    result = router.classify("Log lunch and compare my protein to yesterday.", ["How is my sleep?"])
    assert len(requests) == 1
    body = requests[0]
    assert set(body["state"]) == {"question", "earlier_questions"}
    assert set(body["questions"]["intent"]["criteria"]) == set(Intent)
    assert result.top == "nutrition" and result.intent == Intent.MIXED


@pytest.mark.parametrize("intent", [None, {}, {"type": "noul"}, {"type": "choice"}])
def test_bad_jev_intent_uses_the_fallback_without_repeating_input(intent):
    http = httpx2.Client(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=jev_body(intent)))
    )
    router = FallbackRouter(JevRouter("fake-key", http=http), KeywordRouter())
    result = router.classify("I had rice for lunch.")
    assert result.source == "keyword" and result.intent == Intent.CLARIFY
    assert result.error == "Jev did not return a valid request intent."


def test_llm_baseline_requires_a_valid_intent_and_exposes_the_same_choices():
    args = {
        "topic": {"nutrition": 1},
        "needs": dict.fromkeys(("sleep", "recovery", "activity", "nutrition"), 0),
    }
    with pytest.raises(RouterError, match="every request intent"):
        LLMRouter(ScriptedLLM([ScriptedLLM.call("route", **args)])).classify("Log lunch.")
    llm = ScriptedLLM([ScriptedLLM.call("route", **args, intent=distribution(Intent.LOG))])
    assert LLMRouter(llm).classify("Log lunch.").intent == Intent.LOG
