from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.analysis.evidence import ToolError, Window
from app.analysis.tools import (
    change_point,
    compare_windows,
    correlate,
    coverage,
    describe,
    trend,
    weekday_split,
)
from app.synthetic import Coupling, LowWear, Step, Trend, generate

START = date(2026, 1, 1)


def window(first: int, last: int) -> Window:
    """Window from day `first` to day `last` (0-based, inclusive) after START."""
    return Window(start=START + timedelta(first), end=START + timedelta(last))


def test_window_rejects_reversed_dates():
    with pytest.raises(ValidationError, match="start is after its end"):
        Window(start=date(2026, 2, 1), end=date(2026, 1, 1))


def test_describe_matches_pandas_and_counts_missing_days():
    frame = generate(START, 30, seed=1).frame
    frame.iloc[[2, 5], frame.columns.get_loc("steps")] = np.nan
    evidence = describe(frame, "steps", window(0, 9))
    expected = frame["steps"].iloc[:10].dropna()
    assert evidence.n == 8
    assert evidence.stats["missing_days"] == 2
    assert evidence.stats["mean"] == pytest.approx(expected.mean(), abs=1e-3)
    assert evidence.stats["median"] == pytest.approx(expected.median(), abs=1e-3)
    assert evidence.sufficient


def test_describe_flags_too_few_days():
    frame = generate(START, 30).frame
    frame.loc[:, "hrv_ms"] = np.nan
    evidence = describe(frame, "hrv_ms", window(0, 9))
    assert evidence.n == 0
    assert evidence.stats["mean"] is None
    assert not evidence.sufficient


def test_unknown_metric_is_a_tool_error():
    with pytest.raises(ToolError, match="Unknown metric"):
        describe(generate(START, 10).frame, "vo2max", window(0, 9))


def test_evidence_ids_are_unique():
    frame = generate(START, 10).frame
    assert describe(frame, "steps", window(0, 9)).id != describe(frame, "steps", window(0, 9)).id


def test_coverage_reports_gaps_and_low_wear_days():
    effects = (LowWear(START + timedelta(3), START + timedelta(4)),)
    frame = generate(START, 10, effects).frame
    frame.iloc[:5, frame.columns.get_loc("hrv_ms")] = np.nan
    evidence = coverage(frame, window(0, 9))
    assert evidence.stats["fraction_present"]["hrv_ms"] == 0.5
    assert evidence.stats["fraction_present"]["steps"] == 1.0
    assert evidence.stats["low_wear_days"] == ["2026-01-04", "2026-01-05"]


def test_compare_detects_planted_step():
    frame = generate(START, 60, (Step("resting_hr", START + timedelta(30), 5),), seed=2).frame
    evidence = compare_windows(frame, "resting_hr", window(30, 59), window(0, 29))
    assert evidence.sufficient
    assert evidence.stats["difference"] == pytest.approx(5, abs=1.5)
    assert evidence.stats["cliffs_delta"] > 0.8
    assert evidence.stats["p_value"] < 0.001


def test_compare_false_positive_rate_stays_near_alpha():
    p_values = [
        compare_windows(
            generate(START, 60, seed=seed).frame, "resting_hr", window(30, 59), window(0, 29)
        ).stats["p_value"]
        for seed in range(200)
    ]
    assert np.mean(np.array(p_values) < 0.05) < 0.08


def test_compare_flags_short_windows():
    frame = generate(START, 20).frame
    evidence = compare_windows(frame, "steps", window(15, 19), window(0, 14))
    assert not evidence.sufficient
    assert evidence.stats["n_recent"] == 5


def test_compare_handles_constant_values():
    frame = generate(START, 20).frame
    frame["readiness"] = 70.0
    evidence = compare_windows(frame, "readiness", window(10, 19), window(0, 9))
    assert evidence.stats["p_value"] == 1.0
    assert evidence.stats["cliffs_delta"] == 0.0


def test_compare_rejects_overlapping_windows():
    with pytest.raises(ToolError, match="overlap"):
        compare_windows(generate(START, 20).frame, "steps", window(5, 19), window(0, 9))


def test_compare_with_empty_window_reports_no_statistics():
    frame = generate(START, 20).frame
    frame.loc[pd.Timestamp(START) :, "hrv_ms"] = np.nan
    evidence = compare_windows(frame, "hrv_ms", window(10, 19), window(0, 9))
    assert evidence.stats["p_value"] is None
    assert evidence.stats["pct_change"] is None
    assert not evidence.sufficient


def test_trend_recovers_planted_drift():
    effect = Trend("hrv_ms", START, START + timedelta(59), -12)
    results = [
        trend(generate(START, 60, (effect,), seed=seed).frame, "hrv_ms", window(0, 59))
        for seed in range(200)
    ]
    assert all(evidence.sufficient for evidence in results)
    changes = [evidence.stats["change_over_window"] for evidence in results]
    assert np.mean(changes) == pytest.approx(-12, abs=1)  # unbiased
    covered = [e.stats["slope_low"] <= -12 / 59 <= e.stats["slope_high"] for e in results]
    assert 0.9 <= np.mean(covered) <= 0.99  # the 95% interval holds the true slope ~95% of the time
    assert np.mean([e.stats["p_value"] < 0.05 for e in results]) > 0.85  # power


def test_trend_false_positive_rate_stays_near_alpha():
    p_values = [
        trend(generate(START, 60, seed=seed).frame, "hrv_ms", window(0, 59)).stats["p_value"]
        for seed in range(200)
    ]
    assert np.mean(np.array(p_values) < 0.05) < 0.08


def test_trend_flags_short_windows_and_handles_constants():
    frame = generate(START, 30).frame
    frame["readiness"] = 70.0
    assert not trend(frame, "steps", window(0, 9)).sufficient
    flat = trend(frame, "readiness", window(0, 29))
    assert flat.stats["slope_per_day"] == 0.0
    assert flat.stats["p_value"] == 1.0


def test_correlate_finds_planted_lag():
    effect = Coupling("bedtime_hour", "sleep_efficiency", lag_days=1, strength=-0.8)
    results = [
        correlate(
            generate(START, 90, (effect,), seed=seed).frame,
            "bedtime_hour",
            "sleep_efficiency",
            window(0, 89),
            max_lag=3,
        )
        for seed in range(100)
    ]
    assert all(evidence.sufficient for evidence in results)
    assert all(evidence.stats["lags_tested"] == 4 for evidence in results)
    assert np.mean([e.stats["best_lag"] == 1 for e in results]) > 0.95
    assert np.median([e.stats["rho"] for e in results]) < -0.5
    assert np.mean([e.stats["p_value_adjusted"] < 0.05 for e in results]) > 0.95


def test_correlate_adjusts_p_value_for_lags_tried():
    frame = generate(START, 60, seed=6).frame
    evidence = correlate(frame, "steps", "resting_hr", window(0, 59), max_lag=4)
    raw, adjusted = evidence.stats["p_value"], evidence.stats["p_value_adjusted"]
    assert adjusted == pytest.approx(min(1.0, raw * 5), abs=1e-5)


def test_correlate_false_positive_rate_stays_near_alpha():
    adjusted = [
        correlate(
            generate(START, 60, seed=seed).frame, "steps", "resting_hr", window(0, 59), max_lag=7
        ).stats["p_value_adjusted"]
        for seed in range(200)
    ]
    assert np.mean(np.array(adjusted) < 0.05) < 0.08


def test_correlate_uses_driver_values_from_before_the_window():
    frame = generate(START, 30, seed=7).frame
    evidence = correlate(frame, "steps", "calories", window(10, 29), max_lag=2)
    assert all(lag in evidence.stats["rho_by_lag"] for lag in (0, 1, 2))
    assert evidence.n == 20


def test_correlate_with_no_data_reports_nothing():
    frame = generate(START, 30).frame
    frame["hrv_ms"] = np.nan
    evidence = correlate(frame, "steps", "hrv_ms", window(0, 29))
    assert evidence.stats["rho"] is None
    assert evidence.n == 0
    assert not evidence.sufficient


@pytest.mark.parametrize(
    ("driver", "target", "max_lag", "message"),
    [
        ("steps", "steps", 0, "must be different"),
        ("steps", "calories", 15, "max_lag"),
        ("steps", "calories", -1, "max_lag"),
        ("vo2max", "calories", 0, "Unknown metric"),
    ],
)
def test_correlate_rejects_bad_arguments(driver, target, max_lag, message):
    with pytest.raises(ToolError, match=message):
        correlate(generate(START, 30).frame, driver, target, window(0, 29), max_lag)


def test_change_point_finds_the_day_of_a_planted_step():
    hits = []
    for seed in range(100):
        frame = generate(
            START, 60, (Step("resting_hr", START + timedelta(35), 3),), seed=seed
        ).frame
        evidence = change_point(frame, "resting_hr", window(0, 59))
        found = date.fromisoformat(evidence.stats["change_date"])
        hits.append(
            abs((found - (START + timedelta(35))).days) <= 3 and evidence.stats["p_value"] < 0.05
        )
    assert np.mean(hits) > 0.85  # a 1.5 SD step is found within 3 days nearly every time


def test_change_point_reports_the_levels_on_each_side():
    frame = generate(START, 60, (Step("resting_hr", START + timedelta(30), 6),), seed=4).frame
    stats = change_point(frame, "resting_hr", window(0, 59)).stats
    assert stats["difference"] == pytest.approx(6, abs=1.5)
    assert stats["n_before"] + stats["n_after"] == 60


def test_change_point_false_positive_rate_stays_near_alpha():
    # Searching every split would make a plain test far too optimistic; the permutation test
    # over the whole search must not be.
    p_values = [
        change_point(generate(START, 60, seed=seed).frame, "resting_hr", window(0, 59)).stats[
            "p_value"
        ]
        for seed in range(200)
    ]
    assert np.mean(np.array(p_values) < 0.05) < 0.08


def test_change_point_needs_a_week_on_each_side():
    frame = generate(START, 60, seed=1).frame
    short = change_point(frame, "resting_hr", window(0, 12))
    assert not short.sufficient and short.stats["change_date"] is None


def test_change_point_skips_missing_days_and_handles_constants():
    frame = generate(START, 40, (Step("resting_hr", START + timedelta(20), 8),), seed=3).frame
    frame.loc[frame.index[18:23], "resting_hr"] = np.nan
    evidence = change_point(frame, "resting_hr", window(0, 39))
    assert evidence.n == 35
    assert pd.Timestamp(evidence.stats["change_date"]) in frame["resting_hr"].dropna().index

    frame["resting_hr"] = 60.0
    flat = change_point(frame, "resting_hr", window(0, 39))
    assert flat.stats["p_value"] == 1.0 and flat.stats["difference"] == 0


def with_weekend_effect(frame: pd.DataFrame, metric: str, delta: float) -> pd.DataFrame:
    frame = frame.copy()
    frame.loc[frame.index.dayofweek >= 5, metric] += delta
    return frame


def test_weekday_split_finds_a_weekend_difference():
    frame = with_weekend_effect(generate(START, 56, seed=5).frame, "steps", -4000)
    evidence = weekday_split(frame, "steps", window(0, 55))
    assert evidence.sufficient
    assert evidence.stats["n_weekend"] == 16 and evidence.stats["n_weekday"] == 40
    assert evidence.stats["mean_weekend"] < evidence.stats["mean_weekday"]
    assert evidence.stats["p_value"] < 0.01


def test_weekday_split_false_positive_rate_stays_near_alpha():
    p_values = [
        weekday_split(generate(START, 56, seed=seed).frame, "steps", window(0, 55)).stats["p_value"]
        for seed in range(200)
    ]
    assert np.mean(np.array(p_values) < 0.05) < 0.08


def test_weekday_split_needs_enough_weekend_days():
    assert not weekday_split(generate(START, 14, seed=1).frame, "steps", window(0, 13)).sufficient
