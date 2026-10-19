from datetime import date

import pandas as pd
import pytest

from app.synthetic import BASELINES, Coupling, LowWear, Step, Trend, generate

START = date(2026, 1, 1)


def test_same_seed_gives_same_data():
    a = generate(START, 30, seed=7).frame
    b = generate(START, 30, seed=7).frame
    pd.testing.assert_frame_equal(a, b)


def test_shape_matches_ingested_table():
    frame = generate(START, 30).frame
    assert list(frame.columns) == list(BASELINES)
    assert frame.index.name == "date"
    assert frame.index[0] == pd.Timestamp(START)
    assert len(frame) == 30


def test_values_stay_within_bounds():
    frame = generate(START, 120, (Step("steps", date(2026, 2, 1), -50000),)).frame
    for name, b in BASELINES.items():
        assert frame[name].between(b.low, b.high).all(), name
    assert (frame.loc["2026-02-01":, "steps"] == 0).all()


def test_step_shifts_level_from_its_date():
    effect = Step("resting_hr", date(2026, 2, 15), 6)
    planted = generate(START, 90, (effect,), seed=1).frame
    plain = generate(START, 90, seed=1).frame
    diff = planted["resting_hr"] - plain["resting_hr"]
    assert (diff.loc[:"2026-02-14"] == 0).all()
    assert diff.loc["2026-02-15":].round(6).eq(6).all()


def test_trend_ramps_then_holds():
    effect = Trend("hrv_ms", date(2026, 1, 11), date(2026, 1, 21), -10)
    planted = generate(START, 40, (effect,), seed=2).frame
    plain = generate(START, 40, seed=2).frame
    diff = (planted["hrv_ms"] - plain["hrv_ms"]).round(6)
    assert diff.loc["2026-01-10"] == 0
    assert diff.loc["2026-01-16"] == -5
    assert (diff.loc["2026-01-21":] == -10).all()


def test_coupling_makes_target_follow_lagged_driver():
    effect = Coupling("bedtime_hour", "sleep_efficiency", lag_days=1, strength=-0.8)
    frame = generate(START, 120, (effect,), seed=3).frame
    lagged = frame["bedtime_hour"].shift(1).corr(frame["sleep_efficiency"], method="spearman")
    same_day = frame["bedtime_hour"].corr(frame["sleep_efficiency"], method="spearman")
    assert lagged < -0.5
    assert abs(same_day) < 0.3


def test_low_wear_shrinks_activity_but_not_sleep():
    effect = LowWear(date(2026, 1, 10), date(2026, 1, 16), wear_minutes=300)
    planted = generate(START, 30, (effect,), seed=4).frame
    plain = generate(START, 30, seed=4).frame
    days = slice("2026-01-10", "2026-01-16")
    assert (planted.loc[days, "wear_minutes"] == 300).all()
    ratio = planted.loc[days, "steps"] / plain.loc[days, "steps"]
    expected = 300 / plain.loc[days, "wear_minutes"]
    pd.testing.assert_series_equal(ratio, expected, check_names=False)
    pd.testing.assert_series_equal(planted["sleep_minutes"], plain["sleep_minutes"])


def test_effects_are_returned_as_ground_truth():
    effects = (Step("steps", date(2026, 1, 5), 1000),)
    assert generate(START, 10, effects).effects == effects


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="Unknown metric"):
        generate(START, 10, (Step("vo2max", START, 1),))


def test_non_positive_length_is_rejected():
    with pytest.raises(ValueError, match="days must be positive"):
        generate(START, 0)
