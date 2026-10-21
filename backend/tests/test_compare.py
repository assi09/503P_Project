import pandas as pd
import pytest

from app.sync.compare import agreement

DAYS = pd.date_range("2026-07-01", periods=4)


def test_agreement_per_shared_column():
    reference = pd.DataFrame({"steps": [1000, 2000, 3000, 4000], "only_here": 1}, index=DAYS)
    candidate = pd.DataFrame({"steps": [1000, 2010, 3300, None], "extra": 2}, index=DAYS)
    result = agreement(candidate, reference)
    assert list(result.index) == ["steps"]
    row = result.loc["steps"]
    assert row["days"] == 3  # a missing value is not compared
    assert row["within_1pct"] == pytest.approx(2 / 3)  # exact and 0.5% off
    assert row["within_5pct"] == pytest.approx(2 / 3)  # 10% off is not close
    assert row["median_abs_diff"] == 10


def test_zero_reference_counts_only_exact_matches():
    reference = pd.DataFrame({"azm": [0.0, 0.0]}, index=DAYS[:2])
    candidate = pd.DataFrame({"azm": [0.0, 0.004]}, index=DAYS[:2])
    assert agreement(candidate, reference).loc["azm", "within_1pct"] == 0.5


def test_columns_without_overlap_are_skipped():
    reference = pd.DataFrame({"hrv_ms": [50.0, None]}, index=DAYS[:2])
    candidate = pd.DataFrame({"hrv_ms": [None, 48.0]}, index=DAYS[:2])
    assert agreement(candidate, reference).empty
