"""Smart alarm detectors: rare on calm people, reliable on planted changes, over many seeds."""

from datetime import date, timedelta

import pytest

from app.alarms.detect import detect, detect_data
from app.analysis.day import with_scores
from app.synthetic import LowWear, Step, generate

START = date(2026, 7, 1)
END = START + timedelta(days=89)
SEEDS = range(30)


def person(seed, *effects):
    return with_scores(generate(START, 90, effects, seed=seed).frame)


@pytest.fixture(scope="module")
def calm():
    return [person(seed) for seed in SEEDS]


def test_noise_alone_rarely_raises_an_alarm(calm):
    """Day and streak alarms on calm synthetic people, each of 21 days: under 0.75 a week."""
    alarms = days = 0
    for frame in calm:
        for offset in range(21):
            end = START + timedelta(days=68 + offset)
            alarms += len(detect(frame.loc[: str(end)], end, kinds=("day", "streak")))
            days += 1
    assert alarms / days * 7 < 0.75


def test_a_very_short_night_is_usually_caught():
    caught = sum(
        any(
            c.metric == "sleep_minutes"
            for c in detect(person(s, Step("sleep_minutes", END, -150)), END)
        )
        for s in SEEDS
    )
    assert caught / len(SEEDS) >= 0.6


def test_a_resting_heart_rate_rise_for_days_is_usually_caught():
    rise = Step("resting_hr", END - timedelta(days=3), 6)
    found = [
        next((c for c in detect(person(s, rise), END) if c.metric == "resting_hr"), None)
        for s in SEEDS
    ]
    assert sum(c is not None for c in found) / len(SEEDS) >= 0.7
    assert all(c.direction == "up" for c in found if c)


def test_a_better_than_usual_night_is_not_an_alarm():
    long_night = Step("sleep_minutes", END, 150)
    for seed in range(10):
        assert not any(c.metric == "sleep_minutes" for c in detect(person(seed, long_night), END))


def test_a_barely_worn_day_never_triggers_one():
    bad_and_unworn = (Step("sleep_minutes", END, -200), LowWear(END, END))
    for seed in range(10):
        candidates = detect(person(seed, *bad_and_unworn), END, kinds=("day",))
        assert not any(c.metric == "sleep_minutes" for c in candidates)


def test_old_data_raises_only_the_data_alarm():
    frame = person(0, Step("sleep_minutes", END, -200))
    later = END + timedelta(days=3)
    assert [c.key for c in detect(frame, later)] == ["data:stale"]
    assert [c.key for c in detect_data(frame, END, reconnect_needed=True)] == ["data:reconnect"]


def test_one_alarm_per_metric_and_each_carries_its_evidence():
    frame = person(1, Step("resting_hr", END - timedelta(days=3), 8), Step("resting_hr", END, 6))
    candidates = detect(frame, END)
    metrics = [c.metric for c in candidates]
    assert len(metrics) == len(set(metrics))
    assert all(c.evidence and c.evidence[0].metrics[0] == c.metric for c in candidates)
    assert candidates == sorted(candidates, key=lambda c: c.severity, reverse=True)


def test_fewer_alarms_means_fewer_alarms(calm):
    def count(sensitivity):
        return sum(
            len(
                detect(
                    frame.loc[: str(START + timedelta(days=70 + k))],
                    START + timedelta(days=70 + k),
                    sensitivity=sensitivity,
                    kinds=("day",),
                )
            )
            for frame in calm
            for k in range(10)
        )

    assert count("fewer") <= count("normal") <= count("more")
