from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.reports import get_stored_evidence
from app.api.store import LoadedData, analyze, get_data
from app.ingest.takeout import DailyData, IngestError
from app.synthetic import LowWear, MissedNights, Step, generate

START = date(2026, 7, 1)
LOADED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def client_with(data_or_error) -> TestClient:
    app = create_app()

    def override() -> LoadedData:
        if isinstance(data_or_error, Exception):
            raise data_or_error
        return data_or_error

    app.dependency_overrides[get_data] = override
    app.dependency_overrides[get_stored_evidence] = lambda: lambda evidence_id: None
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    effects = (
        LowWear(date(2026, 7, 5), date(2026, 7, 6)),
        MissedNights((date(2026, 7, 10), date(2026, 7, 11))),
    )
    frame = generate(START, 20, effects).frame
    return client_with(analyze(DailyData(frame=frame), LOADED_AT))


@pytest.fixture
def changed_client() -> TestClient:
    # 60 days with resting heart rate up by 6 bpm over the last 14.
    effects = (Step("resting_hr", START + timedelta(days=46), 6),)
    frame = generate(START, 60, effects, seed=1).frame
    return client_with(analyze(DailyData(frame=frame), LOADED_AT))


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


def test_latest_report_uses_the_app_contract(changed_client):
    body = changed_client.get("/reports/latest").json()
    assert set(body) == {
        "id",
        "period",
        "createdAt",
        "headline",
        "findings",
        "questions",
        "evidence",
    }
    [finding] = body["findings"]
    assert set(finding) == {
        "id",
        "title",
        "summary",
        "metric",
        "unit",
        "direction",
        "change",
        "series",
        "highlight",
        "evidenceIds",
    }
    assert finding["title"] == "Resting heart rate went up"
    assert finding["series"][0] == {"date": "2026-07-19", "value": finding["series"][0]["value"]}
    assert body["questions"] == []


def test_every_cited_evidence_is_included_and_resolvable(changed_client):
    body = changed_client.get("/reports/latest").json()
    for finding in body["findings"]:
        for evidence_id in finding["evidenceIds"]:
            included = body["evidence"][evidence_id]
            fetched = changed_client.get(f"/evidence/{evidence_id}").json()
            assert fetched == included
            assert fetched["stats"]["mean_recent"] > fetched["stats"]["mean_baseline"]


def test_evidence_that_was_tested_but_not_reported_can_still_be_fetched(changed_client):
    report = changed_client.get("/reports/latest").json()
    cited = {i for f in report["findings"] for i in f["evidenceIds"]}
    # The screen tested every metric; fetch one that is not part of the report.
    data = changed_client.app.dependency_overrides[get_data]()
    other = next(i for i in data.evidence if i not in cited)
    assert changed_client.get(f"/evidence/{other}").status_code == 200


def test_unknown_evidence_is_a_404_with_the_error_shape(client):
    response = client.get("/evidence/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "This evidence does not exist."}
    }


def test_report_without_enough_history_says_nothing_changed(client):
    body = client.get("/reports/latest").json()
    assert body["findings"] == []
    assert body["headline"].startswith("Nothing changed enough")


def test_cors_lets_the_web_app_rename_and_delete(client):
    for method in ("PATCH", "DELETE"):
        preflight = client.options(
            "/conversations/x",
            headers={"Origin": "http://localhost:8081", "Access-Control-Request-Method": method},
        )
        assert preflight.status_code == 200, method
        assert method in preflight.headers["access-control-allow-methods"]
