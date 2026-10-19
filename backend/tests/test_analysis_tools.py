from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.analysis.evidence import ToolError, Window
from app.analysis.tools import compare_windows, coverage, describe
from app.synthetic import LowWear, Step, generate

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
