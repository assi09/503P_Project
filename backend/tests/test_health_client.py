import json
from datetime import date

import httpx2
import pytest

from app.sync.client import API_BASE, ApiError, HealthClient
from app.sync.google_auth import ReconnectNeeded


class FakeApi:
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


def client(api: FakeApi, **kwargs) -> tuple[HealthClient, list[float]]:
    waits: list[float] = []
    http = httpx2.Client(transport=httpx2.MockTransport(api))
    return HealthClient(lambda: "token", http=http, sleep=waits.append, **kwargs), waits


def ok(body: dict) -> httpx2.Response:
    return httpx2.Response(200, json=body)


def error(status: int, message: str = "boom", headers: dict | None = None) -> httpx2.Response:
    return httpx2.Response(status, json={"error": {"message": message}}, headers=headers)


def test_lists_every_page_and_sends_the_filter():
    api = FakeApi(
        ok({"dataPoints": [{"n": 1}, {"n": 2}], "nextPageToken": "p2"}),
        ok({"dataPoints": [{"n": 3}]}),
    )
    health, _ = client(api)
    points = list(
        health.list_points("sleep", filter='sleep.interval.end_time >= "x"', page_size=25)
    )
    assert [p["n"] for p in points] == [1, 2, 3]
    first, second = api.requests
    assert first.url.path.endswith("/dataTypes/sleep/dataPoints")
    assert first.url.params["filter"] == 'sleep.interval.end_time >= "x"'
    assert first.url.params["pageSize"] == "25"
    assert "pageToken" not in first.url.params
    assert second.url.params["pageToken"] == "p2"
    assert second.url.params["filter"] == first.url.params["filter"]
    assert first.headers["Authorization"] == "Bearer token"


def test_empty_list_has_no_points():
    health, _ = client(FakeApi(ok({})))
    assert list(health.list_points("steps")) == []


def test_rollups_are_split_into_90_day_windows():
    api = FakeApi(*(ok({"rollupDataPoints": [{"w": i}]}) for i in range(3)))
    health, _ = client(api)
    points = health.daily_rollup("steps", date(2026, 1, 1), date(2026, 7, 1))  # 181 days
    assert [p["w"] for p in points] == [0, 1, 2]
    ranges = [json.loads(r.content)["range"] for r in api.requests]
    assert ranges[0]["start"]["date"] == {"year": 2026, "month": 1, "day": 1}
    assert ranges[0]["end"]["date"] == {"year": 2026, "month": 4, "day": 1}  # 90 days later
    assert ranges[-1]["end"]["date"] == {"year": 2026, "month": 7, "day": 1}
    assert all(r.method == "POST" and r.url.path.endswith(":dailyRollUp") for r in api.requests)


def test_short_rollup_types_use_14_day_windows():
    api = FakeApi(*(ok({"rollupDataPoints": []}) for _ in range(3)))
    health, _ = client(api)
    health.daily_rollup("active-minutes", date(2026, 1, 1), date(2026, 1, 31))  # 30 days
    assert len(api.requests) == 3


def test_rollup_follows_pages_within_a_window():
    api = FakeApi(
        ok({"rollupDataPoints": [{"d": 1}], "nextPageToken": "next"}),
        ok({"rollupDataPoints": [{"d": 2}]}),
    )
    health, _ = client(api)
    assert len(health.daily_rollup("steps", date(2026, 1, 1), date(2026, 1, 3))) == 2
    assert json.loads(api.requests[1].content)["pageToken"] == "next"


def test_empty_range_makes_no_request():
    api = FakeApi()
    health, _ = client(api)
    assert health.daily_rollup("steps", date(2026, 1, 2), date(2026, 1, 2)) == []
    assert api.requests == []


def test_rate_limits_are_retried_honoring_retry_after():
    api = FakeApi(error(429, headers={"Retry-After": "7"}), ok({"dataPoints": [{"n": 1}]}))
    health, waits = client(api)
    assert len(list(health.list_points("steps"))) == 1
    assert waits == [7.0]


def test_server_errors_back_off_exponentially_then_give_up():
    api = FakeApi(*(error(503, "unavailable") for _ in range(4)))
    health, waits = client(api, max_retries=3, backoff_s=1.0)
    with pytest.raises(ApiError, match="unavailable") as raised:
        list(health.list_points("steps"))
    assert raised.value.status == 503
    assert waits == [1.0, 2.0, 4.0]
    assert len(api.requests) == 4


def test_network_failures_are_retried():
    api = FakeApi(httpx2.ConnectError("down"), httpx2.ReadTimeout("slow"), ok({"dataPoints": []}))
    health, waits = client(api)
    assert list(health.list_points("steps")) == []
    assert len(waits) == 2


def test_persistent_timeouts_end_in_a_clear_error():
    api = FakeApi(*(httpx2.ReadTimeout("slow") for _ in range(3)))
    health, _ = client(api, max_retries=2)
    with pytest.raises(ApiError, match="too long"):
        list(health.list_points("steps"))


def test_rejected_sign_in_asks_to_reconnect_without_retrying():
    api = FakeApi(error(401))
    health, waits = client(api)
    with pytest.raises(ReconnectNeeded):
        list(health.list_points("steps"))
    assert waits == []


def test_permission_denied_points_at_the_granted_scopes():
    health, _ = client(FakeApi(error(403, "insufficient scope")))
    with pytest.raises(ApiError, match="every permission") as raised:
        list(health.list_points("nutrition-log"))
    assert raised.value.status == 403


def test_other_client_errors_are_not_retried():
    api = FakeApi(error(400, "bad filter"))
    health, waits = client(api)
    with pytest.raises(ApiError, match="bad filter"):
        list(health.list_points("steps", filter="nonsense"))
    assert waits == []


def test_non_json_response_is_an_error():
    health, _ = client(FakeApi(httpx2.Response(200, text="<html>")))
    with pytest.raises(ApiError, match="not JSON"):
        list(health.list_points("steps"))


def test_api_base_is_the_v4_user_collection():
    assert API_BASE == "https://health.googleapis.com/v4/users/me/dataTypes"
