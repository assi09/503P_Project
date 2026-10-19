from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.store import LoadedData, get_data
from app.ingest.takeout import DailyData, IngestError
from app.synthetic import LowWear, MissedNights, generate

START = date(2026, 7, 1)
LOADED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def client_with(data_or_error) -> TestClient:
    app = create_app()

    def override() -> LoadedData:
        if isinstance(data_or_error, Exception):
            raise data_or_error
        return data_or_error

    app.dependency_overrides[get_data] = override
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    effects = (
        LowWear(date(2026, 7, 5), date(2026, 7, 6)),
        MissedNights((date(2026, 7, 10), date(2026, 7, 11))),
    )
    frame = generate(START, 20, effects).frame
    return client_with(LoadedData(daily=DailyData(frame=frame), loaded_at=LOADED_AT))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_data_status_uses_the_app_contract(client):
    response = client.get("/data/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"source", "lastSync", "range", "coverage", "lowWearDays"}
    assert body["source"] == "takeout"
    assert body["lastSync"].startswith("2026-10-19T12:00:00")
    assert body["range"] == {"start": "2026-07-01", "end": "2026-07-20"}
    assert set(body["coverage"][0]) == {"metric", "label", "fractionPresent"}


def test_data_status_reports_real_coverage_and_low_wear_days(client):
    body = client.get("/data/status").json()
    coverage = {c["metric"]: c["fractionPresent"] for c in body["coverage"]}
    assert coverage["steps"] == 1.0
    assert coverage["sleep_minutes"] == 0.9  # two of twenty nights missed
    assert body["lowWearDays"] == ["2026-07-05", "2026-07-06"]


def test_unavailable_data_returns_a_clear_error():
    client = client_with(IngestError("No 'Google Health' folder found under data/raw"))
    response = client.get("/data/status")
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "data_unavailable", "message": "Your Fitbit data could not be loaded."}
    }
    assert "data/raw" not in response.text  # internal paths are not leaked


def test_unknown_routes_use_the_error_shape(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cors_allows_the_web_app_only(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:8081"})
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8081"
    assert "access-control-allow-origin" not in other.headers
