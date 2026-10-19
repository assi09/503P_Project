from datetime import date

import pandas as pd
import pytest

from app.synthetic import (
    BASELINES,
    NIGHTLY,
    Coupling,
    DeviceOff,
    LowWear,
    MissedNights,
    NewDevice,
    Step,
    Trend,
    generate,
)

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
    expected = plain.loc[days, "steps"] * 300 / plain.loc[days, "wear_minutes"]
    # Equal up to rounding: steps and wear minutes are whole numbers.
    pd.testing.assert_series_equal(
        planted.loc[days, "steps"], expected, rtol=2e-3, check_names=False
    )
    pd.testing.assert_series_equal(planted["sleep_minutes"], plain["sleep_minutes"])


def test_effects_are_returned_as_ground_truth():
    effects = (Step("steps", date(2026, 1, 5), 1000),)
    assert generate(START, 10, effects).effects == effects


def test_values_are_rounded_like_fitbit_reports_them():
    frame = generate(START, 60, seed=8).frame
    for name, b in BASELINES.items():
        assert (frame[name] == frame[name].round(b.digits)).all(), name
    assert (frame["steps"] % 1 == 0).all()


def test_sleep_stages_add_up_like_fitbit_sleep_logs():
    frame = generate(START, 120, (Step("sleep_minutes", START, -60),), seed=9).frame
    stages = frame[["deep_sleep_minutes", "light_sleep_minutes", "rem_sleep_minutes"]]
    assert (stages.sum(axis=1) == frame["sleep_minutes"]).all()
    assert (frame["sleep_minutes"] + frame["awake_in_bed_minutes"] == frame["time_in_bed"]).all()
    assert (stages >= 0).all().all()


def test_activity_minutes_fit_in_a_day():
    effect = Step("lightly_active_minutes", START, 900)
    frame = generate(START, 60, (effect,), seed=10).frame
    columns = ["sedentary_minutes", "lightly_active_minutes"]
    columns += ["moderately_active_minutes", "very_active_minutes"]
    assert (frame[columns].sum(axis=1) <= 1440).all()


def test_missed_nights_drop_every_sleep_time_metric_together():
    night = date(2026, 1, 5)
    frame = generate(START, 10, (MissedNights((night,)),)).frame
    row = frame.loc[pd.Timestamp(night)]
    assert row[list(NIGHTLY)].isna().all()
    assert row.drop(list(NIGHTLY)).notna().all()
    assert frame.drop(pd.Timestamp(night)).notna().all().all()


def test_device_off_leaves_whole_days_empty():
    effect = DeviceOff(date(2026, 1, 3), date(2026, 1, 4))
    frame = generate(START, 10, (effect,)).frame
    assert frame.loc["2026-01-03":"2026-01-04"].isna().all().all()
    assert frame.loc["2026-01-05":].notna().all().all()


def test_new_device_has_no_first_night_and_warms_up_baselines():
    frame = generate(START, 20, (NewDevice(),)).frame
    assert frame.iloc[0][list(NIGHTLY)].isna().all()
    assert frame["readiness"].iloc[:7].isna().all()
    assert frame["readiness"].iloc[7:].notna().all()
    assert frame["skin_temp_variation_c"].iloc[:4].isna().all()
    assert frame["steps"].notna().all()


def test_gaps_hide_planted_changes_without_shifting_them():
    step = Step("resting_hr", date(2026, 1, 10), 5)
    plain = generate(START, 20, (step,), seed=11).frame
    gapped = generate(START, 20, (step, DeviceOff(date(2026, 1, 3), date(2026, 1, 4))), seed=11)
    kept = gapped.frame["resting_hr"].dropna()
    pd.testing.assert_series_equal(kept, plain["resting_hr"].loc[kept.index])


def test_derived_metric_cannot_be_targeted():
    with pytest.raises(ValueError, match="derived"):
        generate(START, 10, (Step("time_in_bed", START, 30),))


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="Unknown metric"):
        generate(START, 10, (Step("vo2max", START, 1),))


def test_non_positive_length_is_rejected():
    with pytest.raises(ValueError, match="days must be positive"):
        generate(START, 0)
