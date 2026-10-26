import json

import httpx2
import pytest

from app.agent.intent import Intent, keyword_intent
from app.agent.jev import JEV_PATH
from app.agent.llm import LLMError, ScriptedLLM
from app.agent.router import (
    EXPERT_LABELS,
    GENERAL,
    LABELS,
    OUT_OF_SCOPE,
    Classification,
    FallbackRouter,
    JevRouter,
    KeywordRouter,
    LLMRouter,
    RouterError,
    clean,
    decide,
    normalized,
)


def probabilities(**given: float) -> dict[str, float]:
    return dict.fromkeys(LABELS, 0.0) | given


def needing(*experts: str) -> dict[str, float]:
    return {e: 0.9 if e in experts else 0.05 for e in EXPERT_LABELS}


def classified(needs: tuple[str, ...] = (), **given: float) -> Classification:
    return Classification(probabilities(**given), needing(*needs), source="test")


class FakeJev:
    """Answers requests from a queue of responses and records what was asked."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def jev(api: FakeJev, **kwargs) -> JevRouter:
    http = httpx2.Client(transport=httpx2.MockTransport(api))
    return JevRouter("test-key", http=http, **kwargs)


def choice(probs: dict, needs: dict | None = None, input_tokens: int = 100) -> httpx2.Response:
    top = max(probs, key=probs.get)
    answer = {"type": "choice", "choice": top, "probabilities": probs, "confidence": probs[top]}
    nouls = {f"needs_{e}": {"type": "noul", "noul": p} for e, p in (needs or needing(top)).items()}
    body = {
        "model": "jev-latest",
        "answers": {
            "topic": answer,
            **nouls,
            "intent": {"type": "choice", "probabilities": keyword_intent("How is my sleep?")},
        },
        "usage": {"input_tokens": input_tokens},
    }
    return httpx2.Response(200, json=body)


def test_jev_gets_the_question_only_and_labels_to_choose_from():
    api = FakeJev(choice(probabilities(sleep=0.9, recovery=0.1)))
    jev(api).classify("Why did I sleep less this week?")
    request = api.requests[0]
    assert request.url.path == JEV_PATH and request.method == "POST"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["state"] == "Why did I sleep less this week?"
    assert body["model"] == "jev-latest"
    question = body["questions"]["topic"]
    assert question["type"] == "choice" and set(question["criteria"]) == set(LABELS)
    for expert in EXPERT_LABELS:  # and, separately, whether each expert's data is needed
        needs = body["questions"][f"needs_{expert}"]
        assert needs["type"] == "noul" and expert in needs["instructions"]


def test_jev_probabilities_cost_and_latency_are_recorded():
    ticks = iter([10.0, 10.25])
    needs = needing("sleep", "recovery")
    api = FakeJev(choice(probabilities(sleep=0.7, recovery=0.3), needs, input_tokens=1_000))
    result = jev(api, clock=lambda: next(ticks)).classify("How is my sleep?")
    assert result.source == "jev" and result.top == "sleep"
    assert result.probabilities["recovery"] == pytest.approx(0.3)
    assert result.needs == needs
    assert result.cost_usd == pytest.approx(0.000042)
    assert result.latency_s == pytest.approx(0.25)


def test_missing_labels_count_as_zero_and_probabilities_are_rescaled():
    assert normalized({"sleep": 2 / 3, "recovery": 1 / 3, "made_up": 0.5}) == pytest.approx(
        probabilities(sleep=2 / 3, recovery=1 / 3)
    )
    assert sum(normalized({"sleep": 0.5, "activity": 0.3}).values()) == pytest.approx(1)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx2.ReadTimeout("slow"), "took too long"),
        (httpx2.ConnectError("down"), "Could not reach Jev"),
        (httpx2.Response(401, json={"error": "bad key"}), "rejected the API key"),
        (httpx2.Response(429, json={}), "rate limiting"),
        (httpx2.Response(503, text="unavailable"), r"error \(503\)"),
        (httpx2.Response(200, text="not json"), "expected format"),
        (httpx2.Response(200, json={"answers": {}}), "expected format"),
        (httpx2.Response(200, json={"answers": {"topic": {"type": "noul"}}}), "expected format"),
        (choice({"sleep": -0.2, "recovery": 1.2}), "invalid probability"),
        (choice({"sleep": 0.0, "recovery": 0.0}), "no probabilities"),
        (choice({"sleep": 1.0}, needing("sleep") | {"activity": 1.5}), "needs activity"),
        (
            httpx2.Response(
                200,
                json={"answers": {"topic": {"type": "choice", "probabilities": {"sleep": 1}}}},
            ),
            "expected format",
        ),
    ],
)
def test_jev_failures_become_router_errors(response, message):
    with pytest.raises(RouterError, match=message):
        jev(FakeJev(response)).classify("How is my sleep?")


def test_jev_errors_never_repeat_the_question():
    body = {"error": {"message": "bad state: Why did I sleep so badly"}}
    with pytest.raises(RouterError) as raised:
        jev(FakeJev(httpx2.Response(400, json=body))).classify("Why did I sleep so badly")
    assert "sleep" not in str(raised.value)


def test_jev_needs_a_key():
    with pytest.raises(RouterError, match="FA_TYPESAFE_API_KEY"):
        JevRouter("  ")


def test_only_a_clean_short_question_leaves_the_server():
    assert clean("How\x00 is my\x1b sleep?\n") == "How  is my  sleep?"
    assert len(clean("a" * 2_000)) == 500


@pytest.mark.parametrize(
    ("question", "label"),
    [
        ("Why did I sleep less this week?", "sleep"),
        ("Has my bedtime moved later?", "sleep"),
        ("Why is my HRV low?", "recovery"),
        ("Did my resting heart rate go up?", "recovery"),
        ("Am I walking fewer steps than usual?", "activity"),
        ("How much did I train last month?", "activity"),
        ("Was my stress score higher this week?", "recovery"),
        ("Why was my strain so high on Saturday?", "activity"),
        ("How much protein do I eat?", "nutrition"),
        ("How am I doing overall?", GENERAL),
        ("Do I have insomnia?", OUT_OF_SCOPE),
        ("Should I see a doctor about my heart rate?", OUT_OF_SCOPE),
        ("What medication would help me sleep?", OUT_OF_SCOPE),
        ("Should I take melatonin for it?", OUT_OF_SCOPE),
    ],
)
def test_the_keyword_rule_labels_plain_questions(question, label):
    result = KeywordRouter().classify(question)
    assert result.top == label and result.source == "keyword"


def test_the_keyword_rule_does_not_refuse_questions_about_being_sick():
    result = KeywordRouter().classify("Did my HRV drop when I was sick?")
    assert result.top == "recovery"
    supplements = KeywordRouter().classify(
        "Did my protein-supplement days go with better recovery?"
    )
    assert supplements.top != OUT_OF_SCOPE


def test_the_keyword_rule_says_a_cross_domain_question_needs_both_experts():
    result = KeywordRouter().classify("Did my late nights hurt my recovery?")
    assert result.needs == {"sleep": 1.0, "recovery": 1.0, "activity": 0.0, "nutrition": 0.0}


def test_the_llm_router_reads_probabilities_from_its_tool_call():
    route = ScriptedLLM.call(
        "route",
        cost_usd=0.0001,
        topic=probabilities(activity=1.0),
        needs=needing("activity"),
        intent=keyword_intent("How many steps did I walk?"),
    )
    llm = ScriptedLLM([route])
    result = LLMRouter(llm).classify("How many steps did I walk?")
    assert result.top == "activity" and result.source == "llm" and result.cost_usd == 0.0001
    assert result.needs == needing("activity")
    assert result.intent == Intent.READ
    request = llm.requests[0]
    assert request["tools"] == ["route"]
    assert json.loads(request["messages"][1]["content"]) == {
        "question": "How many steps did I walk?",
        "earlier_questions": [],
    }


def test_the_llm_router_fails_cleanly():
    with pytest.raises(RouterError, match="did not route"):
        LLMRouter(ScriptedLLM([ScriptedLLM.say("sleep, probably")])).classify("x")
    with pytest.raises(RouterError, match="no more turns"):
        LLMRouter(ScriptedLLM([])).classify("x")
    without_needs = ScriptedLLM([ScriptedLLM.call("route", topic=probabilities(sleep=1.0))])
    with pytest.raises(RouterError, match="which experts' data"):
        LLMRouter(without_needs).classify("x")
    assert issubclass(RouterError, RuntimeError) and not issubclass(RouterError, LLMError)


def test_the_fallback_answers_when_jev_fails_and_keeps_the_reason():
    router = FallbackRouter(jev(FakeJev(httpx2.ReadTimeout("slow"))), KeywordRouter())
    result = router.classify("Why is my HRV low?")
    assert result.source == "keyword" and result.top == "recovery"
    assert "took too long" in result.error


def test_no_fallback_when_jev_answers():
    api = FakeJev(choice(probabilities(sleep=1.0)))
    result = FallbackRouter(jev(api), KeywordRouter()).classify("How is my sleep?")
    assert result.source == "jev" and result.error is None


def test_one_clear_label_goes_to_that_expert_alone():
    route = decide(classified(("sleep",), sleep=0.85, recovery=0.1, general=0.05))
    assert (route.action, route.expert, route.consult, route.routed) == (
        "expert",
        "sleep",
        (),
        True,
    )


def test_a_cross_domain_question_is_led_by_the_likeliest_topic_with_consults():
    route = decide(classified(("recovery", "sleep"), recovery=0.7, sleep=0.1, out_of_scope=0.2))
    assert route.expert == "recovery" and route.consult == ("sleep",)


def test_consults_follow_what_the_question_needs_not_the_spare_topic_probability():
    # The topic's leftover probability is uncertainty: it does not make a second expert needed.
    route = decide(classified(("sleep",), sleep=0.6, activity=0.4))
    assert route.expert == "sleep" and route.consult == ()


def test_low_confidence_goes_to_the_general_agent():
    assert decide(classified(sleep=0.35, recovery=0.33, activity=0.32)).action == "general"
    assert decide(classified(general=0.6, sleep=0.4)).action == "general"


def test_out_of_scope_is_refused_even_when_the_person_picked_an_expert():
    assert decide(classified(out_of_scope=0.7, sleep=0.3)).action == "refuse"
    route = decide(classified(out_of_scope=0.7, sleep=0.3), choice="sleep")
    assert route.action == "refuse" and route.expert is None


def test_a_chosen_expert_leads_and_the_router_still_picks_its_consults():
    route = decide(classified(("recovery",), recovery=0.9, sleep=0.1), choice="sleep")
    assert (route.action, route.expert, route.consult, route.routed) == (
        "expert",
        "sleep",
        ("recovery",),
        False,
    )


def test_an_unknown_expert_choice_is_a_programming_error():
    with pytest.raises(ValueError, match="unknown expert"):
        decide(classified(sleep=1.0), choice="cardiology")


def test_jev_sees_up_to_three_earlier_questions_newest_first():
    api = FakeJev(choice(probabilities(sleep=1.0)))
    earlier = ["Has my bedtime moved?", "How is my HRV?", "Steps?", "Oldest\x00 one?"]
    jev(api).classify("And last week?", earlier)
    body = json.loads(api.requests[0].content)
    assert body["state"] == {
        "question": "And last week?",
        "earlier_questions": ["Has my bedtime moved?", "How is my HRV?", "Steps?"],
    }
    assert "current question" in body["questions"]["topic"]["instructions"]


def test_the_keyword_rule_reads_a_follow_up_through_the_latest_question_with_a_topic():
    earlier = ["Thanks!", "Why is my HRV low?", "How many steps did I walk?"]
    result = KeywordRouter().classify("And what about last week?", earlier)
    assert result.top == "recovery"  # "Thanks!" has no topic, so the HRV question decides
    assert KeywordRouter().classify("How is my sleep?", earlier).top == "sleep"  # its own wins


def test_the_fallback_passes_the_earlier_questions_on():
    router = FallbackRouter(jev(FakeJev(httpx2.ReadTimeout("slow"))), KeywordRouter())
    assert router.classify("And last week?", ["Why is my HRV low?"]).top == "recovery"
