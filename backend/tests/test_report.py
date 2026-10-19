import re
from datetime import UTC, date, datetime, timedelta

import pytest

from app.analysis.report import (
    MAX_FINDINGS,
    build_report,
    change_label,
    clock,
    format_value,
)
from app.analysis.screen import RECENT_DAYS, screen
from app.synthetic import MissedNights, Step, generate

START = date(2026, 1, 1)
DAYS = 60
RECENT_START = START + timedelta(DAYS - RECENT_DAYS)
NOW = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


def report_for(effects=(), seed=1):
    frame = generate(START, DAYS, effects, seed=seed).frame
    return build_report(frame, screen(frame), NOW)


def test_clock_wraps_around_midnight():
    assert clock(-0.5) == "23:30"
    assert clock(1.25) == "01:15"
    assert clock(0) == "00:00"


@pytest.mark.parametrize(
    ("metric", "value", "expected"),
    [
        ("steps", 8234.6, "8,235 steps"),
        ("resting_hr", 61.04, "61.0 bpm"),
        ("sleep_efficiency", 91.6, "91.6%"),
        ("readiness", 72.3, "72.3"),
        ("bedtime_hour", 0.75, "00:45"),
    ],
)
def test_values_are_formatted_in_their_unit(metric, value, expected):
    assert format_value(metric, value) == expected


@pytest.mark.parametrize(
    ("metric", "stats", "expected"),
    [
        ("steps", {"difference": 1200, "pct_change": 15.2}, "+15%"),
        ("resting_hr", {"difference": 5.6, "pct_change": 9.1}, "+5.6 bpm"),
        ("sleep_efficiency", {"difference": -5.5, "pct_change": -6.0}, "-5.5%"),
        ("bedtime_hour", {"difference": 0.83, "pct_change": None}, "+50 min"),
        ("skin_temp_variation_c", {"difference": -0.4, "pct_change": None}, "-0.4 °C"),
    ],
)
def test_change_labels(metric, stats, expected):
    assert change_label(metric, stats) == expected


def test_reports_a_planted_change_with_text_backed_by_its_evidence():
    report = report_for((Step("resting_hr", RECENT_START, 6),))
    assert report.headline == f"1 change stood out in the last {RECENT_DAYS} days."
    [finding] = report.findings
    assert finding.title == "Resting heart rate went up"
    assert finding.direction == "up"
    evidence = report.evidence[finding.evidence_ids[0]]
    stats = evidence.stats
    # Every number in the summary is one of the evidence's statistics.
    assert format_value("resting_hr", stats["mean_recent"]) in finding.summary
    assert format_value("resting_hr", stats["mean_baseline"]) in finding.summary
    numbers = re.findall(r"\d+(?:\.\d+)?", finding.summary)
    allowed = {f"{stats['mean_recent']:.1f}", f"{stats['mean_baseline']:.1f}", "14", "28"}
    assert set(numbers) <= allowed


def test_series_covers_the_period_and_keeps_gaps():
    night = RECENT_START + timedelta(days=3)
    report = report_for((Step("sleep_minutes", RECENT_START, -90), MissedNights((night,))), seed=4)
    finding = next(f for f in report.findings if f.metric == "sleep_minutes")
    assert finding.series[0][0] == report.period.start
    assert finding.series[-1][0] == report.period.end
    assert dict(finding.series)[night] is None
    assert finding.highlight.start == RECENT_START


def test_empty_report_says_so():
    report = report_for(seed=5)
    assert report.findings == []
    assert report.evidence == {}
    assert report.headline == f"Nothing changed enough to report in the last {RECENT_DAYS} days."


def test_caps_the_number_of_findings():
    effects = tuple(
        Step(m, RECENT_START, d)
        for m, d in [
            ("resting_hr", 8),
            ("hrv_ms", -15),
            ("steps", 6000),
            ("sleep_minutes", -100),
            ("readiness", -25),
            ("respiratory_rate", 2.5),
            ("calories", 600),
        ]
    )
    report = report_for(effects, seed=6)
    assert len(report.findings) == MAX_FINDINGS
    assert set(report.evidence) == {f.evidence_ids[0] for f in report.findings}
