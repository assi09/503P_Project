"""Strain and stress (docs/scores.md) on made-up days."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.analysis.day import (
    DAYTIME,
    DEFAULT_LOAD_PER_AZM,
    MIN_STILL_MINUTES,
    MIN_USUAL_DAYS,
    STRAIN_MAX,
    STRESS_WEIGHTS,
    ZONE_WEIGHTS,
    strain_band,
    strain_days,
    strain_from_load,
    stress_parts,
    stress_score,
    with_scores,
)

START = date(2026, 7, 1)


def frame_of(values: dict[str, list[float]]) -> pd.DataFrame:
    length = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.date_range(START, periods=length))


def stamp(offset: int) -> pd.Timestamp:
    return pd.Timestamp(START + timedelta(days=offset))


# Strain


def test_strain_grows_with_load_and_never_passes_the_top_of_the_scale():
    loads = np.linspace(0, 2000, 200)
    scores = [strain_from_load(load) for load in loads]
    assert scores[0] == 0
    assert all(a <= b for a, b in zip(scores, scores[1:], strict=False))
    assert scores[-1] <= STRAIN_MAX and strain_from_load(400) < STRAIN_MAX
    # Each extra minute adds less near the top.
    assert strain_from_load(100) - strain_from_load(0) > strain_from_load(400) - strain_from_load(
        300
    )


@pytest.mark.parametrize(
    ("score", "band"),
    [(0, "light"), (9.9, "light"), (10, "moderate"), (14, "high"), (17.9, "high"), (18, "all_out")],
)
def test_strain_bands_follow_whoops(score, band):
    assert strain_band(score) == band


def test_strain_weights_each_zone_and_counts_missing_zones_as_none():
    frame = frame_of(
        {
            "hr_zone_light_minutes": [60.0, 0.0, np.nan],
            "hr_zone_moderate_minutes": [10.0, 0.0, np.nan],
            "hr_zone_vigorous_minutes": [5.0, np.nan, np.nan],
            "hr_zone_peak_minutes": [1.0, 0.0, np.nan],
        }
    )
    found = strain_days(frame)
    weights = [ZONE_WEIGHTS[c] for c in frame.columns]
    expected = round(sum(w * m for w, m in zip(weights, [60, 10, 5, 1], strict=True)), 1)
    assert found[stamp(0)].load == expected and found[stamp(0)].method == "zones"
    assert found[stamp(0)].score == strain_from_load(expected)
    assert found[stamp(1)].score == 0  # worn, no time in any zone
    assert stamp(2) not in found  # no zone data and no fallback: no strain, not zero
    assert set(ZONE_WEIGHTS) == set(frame.columns)


def test_without_zones_strain_is_estimated_from_active_zone_minutes():
    days = MIN_USUAL_DAYS + 2
    # Zone load is exactly 3 times AZM on the days with both; the last day has AZM only.
    frame = frame_of(
        {
            "hr_zone_moderate_minutes": [15.0] * (days - 1) + [np.nan],
            "active_zone_minutes": [10.0] * (days - 1) + [20.0],
        }
    )
    last = strain_days(frame)[stamp(days - 1)]
    assert last.method == "active_zone_minutes" and last.load == 60
    # Too few days with both: the default ratio.
    only_azm = frame_of({"active_zone_minutes": [20.0]})
    assert strain_days(only_azm)[stamp(0)].load == 20 * DEFAULT_LOAD_PER_AZM


# Stress


def stress_frame(days: int, still: list[float], above: list[float], **others) -> pd.DataFrame:
    """Days with the same exercise each day unless `others` says otherwise."""
    values = {"hr_zone_moderate_minutes": [20.0] * days, **others}
    return frame_of({"still_minutes": still, "still_hr_above_resting": above, **values})


def test_a_higher_heart_rate_while_still_means_more_stress():
    days = 30
    still = [500.0] * days
    calm = stress_frame(days, still, [15.0] * (days - 1) + [8.0])
    tense = stress_frame(days, still, [15.0] * (days - 1) + [25.0])
    last = START + timedelta(days=days - 1)
    assert stress_parts(tense, last)[DAYTIME] == 100
    assert stress_parts(calm, last)[DAYTIME] == 0
    assert stress_score(stress_parts(tense, last)) > stress_score(stress_parts(calm, last))


def test_a_typical_day_scores_about_50():
    rng = np.random.default_rng(0)
    days = 200
    frame = stress_frame(
        days,
        [500.0] * days,
        list(rng.normal(15, 3, days)),
        hrv_ms=list(rng.normal(45, 6, days)),
        resting_hr=list(rng.normal(60, 2, days)),
        sleep_minutes=list(rng.normal(420, 40, days)),
    )
    scores = with_scores(frame)["stress_score"].dropna()
    assert len(scores) > 150 and 45 <= scores.median() <= 55
    assert scores.between(0, 100).all()


def test_stress_inputs_point_the_right_way():
    days = 30
    last = START + timedelta(days=days - 1)
    frame = stress_frame(
        days,
        [500.0] * days,
        [50.0] * days,
        hrv_ms=[50.0] * (days - 1) + [30.0],  # lower HRV: more signs of stress
        resting_hr=[60.0] * (days - 1) + [70.0],  # higher resting rate: more
        sleep_minutes=[420.0] * (days - 1) + [300.0],  # less sleep: more
    )
    parts = stress_parts(frame, last)
    assert parts["hrv_ms"] == parts["resting_hr"] == parts["sleep_minutes"] == 100
    assert parts[DAYTIME] == 50  # the same as every day before: ties count half


def test_no_stress_score_without_enough_still_wear_or_a_baseline():
    days = 30
    last = START + timedelta(days=days - 1)
    short = stress_frame(
        days, [500.0] * (days - 1) + [MIN_STILL_MINUTES - 1.0], [50.0] * days, hrv_ms=[50.0] * days
    )
    parts = stress_parts(short, last)
    assert DAYTIME not in parts and "hrv_ms" in parts
    assert stress_score(parts) is None  # the daytime input carries the score
    early = stress_frame(MIN_USUAL_DAYS, [500.0] * MIN_USUAL_DAYS, [50.0] * MIN_USUAL_DAYS)
    assert stress_score(stress_parts(early, START + timedelta(days=MIN_USUAL_DAYS - 1))) is None


def test_a_heart_rate_raised_by_exercise_is_not_read_as_stress():
    # Over many made-up people, still heart rate follows the day's exercise plus noise, and nothing
    # else: stress should not follow strain, while the unadjusted input would.
    correlations = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        days = 120
        moderate = rng.gamma(2, 15, days)
        above = 12 + 3 * np.log1p(2 * moderate) + rng.normal(0, 1, days)
        frame = stress_frame(
            days, [500.0] * days, list(above), hr_zone_moderate_minutes=list(moderate)
        )
        scored = with_scores(frame)
        correlations.append(scored["stress_score"].corr(scored["strain"], method="spearman"))
        assert pd.Series(above).corr(pd.Series(moderate), method="spearman") > 0.5
    assert abs(np.mean(correlations)) < 0.1


def test_stress_weights_renormalize_over_the_inputs_present():
    assert sum(STRESS_WEIGHTS.values()) == pytest.approx(1)
    assert stress_score({DAYTIME: 80.0}) == 80
    both = stress_score({DAYTIME: 100.0, "sleep_minutes": 0.0})
    assert both == round(100 * 0.6 / 0.75)


def test_scores_are_added_once_and_the_metric_endpoint_names_them():
    frame = frame_of({"active_zone_minutes": [30.0] * 3})
    scored = with_scores(frame)
    assert {"recovery_score", "strain", "stress_score"} <= set(scored.columns)
    assert with_scores(scored) is scored
