from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analysis.day import MIN_USUAL_DAYS, RECENT_DAYS, USUAL_DAYS, day_summary, series, usual
from app.api.auth import now
from app.api.main import create_app
from app.api.store import analyze, get_data
from app.ingest.takeout import DailyData
from app.synthetic import LowWear, generate

START = date(2026, 7, 1)
LOADED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def frame_of(values: dict[str, list[float]], start: date = START) -> pd.DataFrame:
    length = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.date_range(start, periods=length))


def test_usual_is_the_middle_half_of_the_days_before_and_skips_the_day_itself():
    # 28 days of 1..28, then the day itself far outside them.
    frame = frame_of({"resting_hr": [*range(1, 29), 500.0]})
    day = START + timedelta(days=28)
    (metric,) = day_summary(frame, day)
    assert metric.value == 500
    assert metric.usual.median == 14.5 and metric.usual.days == USUAL_DAYS
    assert (metric.usual.low, metric.usual.high) == (7.75, 21.25)
    assert len(metric.recent) == RECENT_DAYS and metric.recent[-1] == 500


def test_only_the_28_days_before_count_and_gaps_stay_gaps():
    values = [1000.0] * 10 + [60.0] * 28 + [np.nan]
    frame = frame_of({"resting_hr": values})
    (metric,) = day_summary(frame, START + timedelta(days=38))
    assert metric.value is None and metric.usual.median == 60
    assert metric.recent[-1] is None


def test_too_few_days_give_no_usual_range():
    frame = frame_of({"resting_hr": [60.0] * (MIN_USUAL_DAYS - 1) + [61.0]})
    (metric,) = day_summary(frame, START + timedelta(days=MIN_USUAL_DAYS - 1))
    assert metric.usual is None
    assert usual(pd.Series([1.0] * MIN_USUAL_DAYS)) is not None


def test_low_wear_days_are_left_out_of_activity_but_the_day_keeps_its_value():
    steps = [10_000.0] * 28 + [500.0]
    wear = [900.0] * 20 + [100.0] * 8 + [100.0]  # the last 8 usual days barely worn
    frame = frame_of({"steps": steps, "wear_minutes": wear, "resting_hr": [60.0] * 29})
    metrics = {m.metric: m for m in day_summary(frame, START + timedelta(days=28))}
    assert metrics["steps"].value == 500  # shown as it is; the API flags the day
    assert metrics["steps"].usual.days == 20  # only the well-worn days
    assert metrics["steps"].recent[-1] is None  # the trend line skips a low-wear day
    assert metrics["resting_hr"].usual.days == 28  # heart rate does not depend on wear


def test_series_covers_the_span_ending_on_the_day():
    frame = frame_of({"resting_hr": [60.0, np.nan, 62.0]})
    points = series(frame, "resting_hr", START + timedelta(days=2), 7)
    assert len(points) == 7 and points[-1] == (START + timedelta(days=2), 62.0)
    assert points[-2][1] is None and points[0][1] is None  # before the data: gaps


def client_for(frame: pd.DataFrame, today: datetime | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_data] = lambda: analyze(DailyData(frame=frame), LOADED_AT)
    if today:
        app.dependency_overrides[now] = lambda: today
    return TestClient(app)


@pytest.fixture
def synthetic() -> pd.DataFrame:
    effects = (LowWear(START + timedelta(days=40), START + timedelta(days=40)),)
    return generate(START, 45, effects).frame


def test_day_endpoint_uses_the_app_contract(synthetic):
    last = START + timedelta(days=44)
    client = client_for(synthetic, today=datetime(2026, 8, 14, 9, tzinfo=UTC))
    body = client.get(f"/days/{last.isoformat()}").json()
    assert set(body) == {"date", "partial", "lowWear", "first", "last", "metrics"}
    assert body["partial"] is True and body["lowWear"] is False  # Aug 14 is today, Beirut
    assert (body["first"], body["last"]) == (START.isoformat(), last.isoformat())
    steps = next(m for m in body["metrics"] if m["metric"] == "steps")
    assert set(steps) == {"metric", "value", "usual", "recent"}
    assert set(steps["usual"]) == {"median", "low", "high", "days"}
    assert len(steps["recent"]) == RECENT_DAYS
    assert client.get("/days/latest").json()["date"] == last.isoformat()
    worn_little = client.get(f"/days/{(START + timedelta(days=40)).isoformat()}").json()
    assert worn_little["lowWear"] is True and worn_little["partial"] is False


def test_days_outside_the_data_and_unknown_metrics_are_404(synthetic):
    client = client_for(synthetic)
    assert client.get("/days/2026-01-01").json()["error"]["code"] == "no_data"
    assert client.get("/days/not-a-date").status_code == 422
    assert client.get("/metrics/made_up").json()["error"]["code"] == "unknown_metric"


def test_metric_endpoint_gives_the_span_and_the_usual_range(synthetic):
    client = client_for(synthetic)
    body = client.get("/metrics/resting_hr").json()
    assert len(body["points"]) == 30 and body["points"][-1]["date"] == "2026-08-14"
    assert body["usual"]["days"] == USUAL_DAYS
    shorter = client.get("/metrics/resting_hr", params={"days": 7, "end": "2026-07-20"}).json()
    assert [p["date"] for p in shorter["points"]][-1] == "2026-07-20" and len(
        shorter["points"]
    ) == 7
    # A future end is clamped to the last day; spans are bounded.
    assert (
        client.get("/metrics/resting_hr", params={"end": "2030-01-01"}).json()["points"][-1]["date"]
        == "2026-08-14"
    )
    assert client.get("/metrics/resting_hr", params={"days": 2}).status_code == 422


def test_days_need_an_approved_sign_in(synthetic):
    app = create_app()
    assert TestClient(app).get("/days/2026-07-10").status_code == 401
