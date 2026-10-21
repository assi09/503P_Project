from datetime import date

import pytest

from app.agent.present import (
    clock,
    display,
    duration,
    format_change,
    format_level,
    label,
    metric_list,
    short_date,
)
from app.analysis.evidence import Evidence, Window


@pytest.mark.parametrize(
    "minutes, text", [(45, "45 min"), (432, "7 h 12 min"), (480, "8 h"), (-52.4, "52 min")]
)
def test_durations_read_as_hours_and_minutes(minutes, text):
    assert duration(minutes) == text


@pytest.mark.parametrize(
    "hours, text", [(-0.5, "23:30"), (0.38, "00:23"), (1.25, "01:15"), (0, "00:00")]
)
def test_bedtimes_read_as_clock_times(hours, text):
    assert clock(hours) == text


@pytest.mark.parametrize(
    "metric, value, level, change",
    [
        ("sleep_minutes", 431.6, "7 h 12 min", "7 h 12 min"),
        ("bedtime_hour", -0.48, "23:31", "29 min"),
        ("steps", 8243.4, "8,243", "8,243"),
        ("resting_hr", 61.42, "61.4 bpm", "61.4 bpm"),
        ("sleep_efficiency", 91.6, "91.6%", "91.6%"),
        ("hrv_ms", -7.7, "-7.7 ms", "7.7 ms"),
    ],
)
def test_levels_and_changes_use_the_metric_unit(metric, value, level, change):
    assert format_level(metric, value) == level
    assert format_change(metric, value) == change


def test_labels_are_what_people_call_metrics():
    assert label("sleep_minutes") == "time asleep"
    assert label("bedtime_hour") == "bedtime"
    assert label("something_new") == "something new"
    assert metric_list(["hrv_ms"]) == "hrv_ms (heart rate variability (HRV))"


def test_dates_read_short():
    assert short_date(date(2026, 8, 15)) == "Aug 15"
    assert short_date("2026-09-03") == "Sep 3"


def test_display_formats_an_evidence_without_changing_it():
    evidence = Evidence(
        tool="compare_windows",
        metrics=("bedtime_hour",),
        windows=(
            Window(start=date(2026, 8, 16), end=date(2026, 8, 29)),
            Window(start=date(2026, 7, 19), end=date(2026, 8, 15)),
        ),
        n=42,
        sufficient=True,
        stats={
            "mean_recent": 0.38,
            "mean_baseline": -0.48,
            "difference": 0.86,
            "pct_change": 179.2,
            "p_value": 0.001,
        },
    )
    shown = display(evidence)
    assert shown["mean_recent"] == "00:23" and shown["mean_baseline"] == "23:31"
    assert shown["difference"] == "52 min" and shown["pct_change"] == "179%"
    assert shown["windows"] == "Aug 16 to Aug 29, Jul 19 to Aug 15"
    assert "p_value" not in shown
    assert evidence.stats["mean_recent"] == 0.38  # the data is untouched
