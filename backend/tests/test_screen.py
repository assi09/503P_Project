from datetime import date, timedelta

import numpy as np
import pytest

from app.analysis.screen import (
    BASELINE_DAYS,
    RECENT_DAYS,
    benjamini_hochberg,
    screen,
    screen_windows,
)
from app.analysis.tools import compare_windows
from app.synthetic import LowWear, Step, generate

START = date(2026, 1, 1)
DAYS = 60
RECENT_START = START + timedelta(DAYS - RECENT_DAYS)


def test_windows_are_the_last_days_and_the_weeks_before():
    recent, baseline = screen_windows(generate(START, DAYS).frame)
    assert (recent.start, recent.end) == (RECENT_START, START + timedelta(DAYS - 1))
    assert baseline.end == recent.start - timedelta(days=1)
    assert baseline.days == BASELINE_DAYS and recent.days == RECENT_DAYS


def test_benjamini_hochberg_matches_the_textbook_example():
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.005])
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_benjamini_hochberg_never_exceeds_one():
    assert max(benjamini_hochberg([0.9, 0.95, 0.99])) <= 1.0


def test_finds_a_planted_change():
    frame = generate(START, DAYS, (Step("resting_hr", RECENT_START, 6),), seed=1).frame
    result = screen(frame)
    assert [c.metric for c in result.changes] == ["resting_hr"]
    change = result.changes[0]
    assert change.q_value < 0.05
    assert change.evidence.stats["difference"] == pytest.approx(6, abs=1.5)


def test_strongest_changes_come_first():
    effects = (
        Step("resting_hr", RECENT_START, 8),
        Step("hrv_ms", RECENT_START, -6),
    )
    result = screen(generate(START, DAYS, effects, seed=2).frame)
    deltas = [abs(c.evidence.stats["cliffs_delta"]) for c in result.changes]
    assert deltas == sorted(deltas, reverse=True)
    assert {"resting_hr", "hrv_ms"} <= {c.metric for c in result.changes}


def test_rarely_reports_anything_without_a_change():
    reported = [len(screen(generate(START, DAYS, seed=seed).frame).changes) for seed in range(100)]
    assert np.mean(np.array(reported) > 0) < 0.1  # any false finding in under 10% of people


def test_low_wear_days_do_not_look_like_activity_drops():
    effects = (LowWear(RECENT_START, RECENT_START + timedelta(days=7), wear_minutes=200),)
    frame = generate(START, DAYS, effects, seed=3).frame
    recent, baseline = screen_windows(frame)
    # Without excluding those days, steps would look like a significant drop.
    assert compare_windows(frame, "steps", recent, baseline).stats["p_value"] < 0.01
    activity = {"steps", "calories", "distance_km", "cardio_load", "sedentary_minutes"}
    assert not activity & {c.metric for c in screen(frame).changes}


def test_every_metric_is_tested_except_quality_signals():
    result = screen(generate(START, DAYS).frame)
    tested = {e.metrics[0] for e in result.tested}
    assert "wear_minutes" not in tested and "time_in_bed" not in tested
    assert {"steps", "resting_hr", "sleep_minutes"} <= tested


def test_evidence_records_the_adjusted_p_value_it_was_judged_on():
    frame = generate(START, DAYS, (Step("resting_hr", RECENT_START, 6),), seed=1).frame
    result = screen(frame)
    [change] = result.changes
    stats = change.evidence.stats
    assert stats["p_value_adjusted"] == change.q_value
    assert stats["p_value_adjusted"] >= stats["p_value"]
    assert stats["metrics_tested"] == len(result.tested)
    assert change.evidence in result.tested  # the served evidence is the adjusted one
