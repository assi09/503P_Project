import json

import httpx2
import pytest

from app.agent.guard import FLAG_AT, MAX_TEXTS, REASON, GuardError, JevGuard, Judgement
from app.agent.jev import JevClient


def guard(*responses) -> tuple[JevGuard, list[httpx2.Request]]:
    requests: list[httpx2.Request] = []
    queue = list(responses)

    def api(request):
        requests.append(request)
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    http = httpx2.Client(transport=httpx2.MockTransport(api))
    return JevGuard(JevClient("test-key", http)), requests


def nouls(*probabilities: float, input_tokens: int = 200) -> httpx2.Response:
    answers = {f"advice_{i}": {"type": "noul", "noul": p} for i, p in enumerate(probabilities)}
    return httpx2.Response(200, json={"answers": answers, "usage": {"input_tokens": input_tokens}})


def test_every_sentence_gets_its_own_yes_no_in_one_call():
    checker, requests = guard(nouls(0.9, 0.1))
    judgement = checker.judge(["Cutting caffeine should help.", "Your sleep got shorter."])
    assert judgement.flagged == (True, False)
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["state"] == {
        "sentences": {"0": "Cutting caffeine should help.", "1": "Your sleep got shorter."}
    }
    assert set(body["questions"]) == {"advice_0", "advice_1"}
    assert all(q["type"] == "noul" for q in body["questions"].values())
    assert "sentence 1" in body["questions"]["advice_1"]["instructions"]


def test_the_threshold_and_cost():
    checker, _ = guard(nouls(FLAG_AT, FLAG_AT - 0.01, input_tokens=1_000))
    judgement = checker.judge(["a", "b"])
    assert judgement.flagged == (True, False)
    assert judgement.cost_usd == pytest.approx(0.000042)


def test_nothing_to_check_costs_no_call():
    checker, requests = guard()
    assert checker.judge([]) == Judgement((), ()) and requests == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx2.ReadTimeout("slow"), "took too long"),
        (httpx2.Response(500, text="boom"), r"error \(500\)"),
        (httpx2.Response(200, json={"answers": {}}), "expected format"),
        (nouls(1.5), "invalid probability"),
    ],
)
def test_failures_become_guard_errors(response, message):
    checker, _ = guard(response)
    with pytest.raises(GuardError, match=message):
        checker.judge(["Your sleep got shorter."])


def test_too_many_sentences_at_once_are_refused_before_calling():
    checker, requests = guard()
    with pytest.raises(GuardError, match="At most"):
        checker.judge(["x"] * (MAX_TEXTS + 1))
    assert requests == []


def test_the_reason_tells_the_model_what_to_do_instead():
    assert "suggest only everyday habits grounded in it" in REASON
    assert "doctor" in REASON
