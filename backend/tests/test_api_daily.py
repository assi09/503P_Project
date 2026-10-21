from datetime import date

import pandas as pd
import pytest

from app.sync import daily
from app.sync.daily import NOT_IN_API, load_daily

# Made-up API responses in the shapes the Google Health API returns.
START, END = date(2026, 7, 1), date(2026, 7, 4)  # three local days


def civil(day: str) -> dict:
    y, m, d = map(int, day.split("-"))
    return {"date": {"year": y, "month": m, "day": d}, "time": {}}


def rollup(day: str, field: str, value: dict) -> dict:
    return {"civilStartTime": civil(day), "civilEndTime": civil(day), field: value}


def sleep(start, end, asleep, main=True, kind="STAGES", stages=None, offset="10800s"):
    stages = stages or {"DEEP": 80, "LIGHT": 200, "REM": 100, "AWAKE": 30}
    return {
        "sleep": {
            "interval": {
                "startTime": start,
                "startUtcOffset": offset,
                "endTime": end,
                "endUtcOffset": offset,
            },
            "type": kind,
            "metadata": {"mainSleep": main} if main else {},
            "summary": {
                "minutesAsleep": str(asleep),
                "stagesSummary": [{"type": t, "minutes": str(m)} for t, m in stages.items()],
            },
        }
    }


def level_interval(day: str, start: str, end: str) -> dict:
    return {
        "activityLevel": {
            "interval": {"startTime": start, "endTime": end, "civilStartTime": civil(day)},
            "activityLevelType": "SEDENTARY",
        }
    }


class FakeHealth:
    def __init__(self, rollups=None, points=None):
        self.rollups = rollups or {}
        self.points = points or {}
        self.filters: dict[str, str | None] = {}

    def daily_rollup(self, data_type, start, end):
        return self.rollups.get(data_type, [])

    def list_points(self, data_type, filter=None, page_size=None):
        self.filters[data_type] = filter
        return iter(self.points.get(data_type, []))


@pytest.fixture
def health() -> FakeHealth:
    return FakeHealth(
        rollups={
            "steps": [
                rollup("2026-07-01", "steps", {"countSum": "8000"}),
                {"civilStartTime": civil("2026-07-02")},
            ],
            "distance": [rollup("2026-07-01", "distance", {"millimetersSum": "5500000"})],
            "total-calories": [rollup("2026-07-01", "totalCalories", {"kcalSum": 2400.5})],
            "active-zone-minutes": [
                rollup(
                    "2026-07-01",
                    "activeZoneMinutes",
                    {
                        "sumInFatBurnHeartZone": "10",
                        "sumInCardioHeartZone": "8",
                        "sumInPeakHeartZone": "2",
                    },
                )
            ],
            "active-minutes": [
                rollup(
                    "2026-07-01",
                    "activeMinutes",
                    {
                        "activeMinutesRollupByActivityLevel": [
                            {"activityLevel": "LIGHT", "activeMinutesSum": "150"},
                            {"activityLevel": "MODERATE", "activeMinutesSum": "20"},
                            {"activityLevel": "SOMETHING_NEW", "activeMinutesSum": "5"},
                        ]
                    },
                )
            ],
        },
        points={
            "daily-resting-heart-rate": [
                {
                    "dailyRestingHeartRate": {
                        "date": civil("2026-07-02")["date"],
                        "beatsPerMinute": "61",
                    }
                }
            ],
            "daily-heart-rate-variability": [
                {
                    "dailyHeartRateVariability": {
                        "date": civil("2026-07-02")["date"],
                        "averageHeartRateVariabilityMilliseconds": 45.5,
                    }
                }
            ],
            "daily-sleep-temperature-derivations": [
                {
                    "dailySleepTemperatureDerivations": {
                        "date": civil("2026-07-02")["date"],
                        "nightlyTemperatureCelsius": 33.4,
                        "baselineTemperatureCelsius": 33.1,
                    }
                },
                {  # no baseline yet: no variation
                    "dailySleepTemperatureDerivations": {
                        "date": civil("2026-07-03")["date"],
                        "nightlyTemperatureCelsius": 33.0,
                    }
                },
            ],
            "activity-level": [
                level_interval("2026-07-01", "2026-07-01T06:00:00Z", "2026-07-01T06:30:00Z"),
                level_interval("2026-07-01", "2026-07-01T07:00:00Z", "2026-07-01T07:15:00Z"),
                level_interval("2026-06-30", "2026-06-30T20:00:00Z", "2026-06-30T21:00:00Z"),
            ],
            "sleep": [
                # 23:30 local on Jul 1 to 07:30 local on Jul 2 (UTC+3): the night of Jul 2.
                sleep("2026-07-01T20:30:00Z", "2026-07-02T04:30:00Z", asleep=420),
                sleep("2026-07-02T12:00:00Z", "2026-07-02T13:00:00Z", asleep=55, main=False),  # nap
                # Two main sleeps ending Jul 3: the longer one wins.
                sleep("2026-07-02T22:00:00Z", "2026-07-03T01:00:00Z", asleep=170),
                sleep("2026-07-03T01:30:00Z", "2026-07-03T06:30:00Z", asleep=280, kind="CLASSIC"),
                # Ends on Jul 4 local: outside the range asked for.
                sleep("2026-07-03T21:30:00Z", "2026-07-04T05:00:00Z", asleep=400),
            ],
        },
    )


def day(frame: pd.DataFrame, when: str) -> pd.Series:
    return frame.loc[pd.Timestamp(when)]


def test_rollups_are_converted_to_the_daily_units(health):
    row = day(load_daily(health, START, END).frame, "2026-07-01")
    assert row["steps"] == 8000
    assert row["distance_km"] == 5.5
    assert row["calories"] == 2400.5
    assert row["active_zone_minutes"] == 20  # cardio and peak already count double


def test_a_day_without_rollup_data_is_missing_not_zero(health):
    assert pd.isna(day(load_daily(health, START, END).frame, "2026-07-02")["steps"])


def test_active_minutes_by_level_with_absent_levels_as_zero(health):
    row = day(load_daily(health, START, END).frame, "2026-07-01")
    assert row["lightly_active_minutes"] == 150
    assert row["moderately_active_minutes"] == 20
    assert row["very_active_minutes"] == 0


def test_daily_values_keep_their_date(health):
    row = day(load_daily(health, START, END).frame, "2026-07-02")
    assert row["resting_hr"] == 61
    assert row["hrv_ms"] == 45.5


def test_skin_temperature_is_relative_to_the_baseline(health):
    frame = load_daily(health, START, END).frame
    assert day(frame, "2026-07-02")["skin_temp_variation_c"] == pytest.approx(0.3)
    assert pd.isna(day(frame, "2026-07-03")["skin_temp_variation_c"])


def test_wear_time_sums_interval_minutes_within_the_range(health):
    frame = load_daily(health, START, END).frame
    assert day(frame, "2026-07-01")["wear_minutes"] == 45
    assert pd.Timestamp("2026-06-30") not in frame.index


def test_sleep_is_dated_by_the_local_day_it_ended(health):
    row = day(load_daily(health, START, END).frame, "2026-07-02")
    assert row["sleep_minutes"] == 420
    assert row["time_in_bed"] == 480
    assert row["sleep_efficiency"] == 88  # 420 of 480 minutes
    assert row["bedtime_hour"] == -0.5  # 23:30 local
    assert row["deep_sleep_minutes"] == 80
    assert row["awake_in_bed_minutes"] == 30


def test_longest_main_sleep_wins_and_classic_nights_have_no_stages(health):
    row = day(load_daily(health, START, END).frame, "2026-07-03")
    assert row["sleep_minutes"] == 280
    assert pd.isna(row["deep_sleep_minutes"])


def test_sleep_outside_the_range_is_left_out(health):
    frame = load_daily(health, START, END).frame
    assert list(frame.index.strftime("%m-%d")) == ["07-01", "07-02", "07-03"]


def test_columns_the_api_lacks_are_reported_missing(health):
    data = load_daily(health, START, END)
    assert set(NOT_IN_API) <= set(data.missing)
    assert "respiratory_rate" in data.missing  # no points in this fake
    assert "steps" not in data.missing
    assert "sedentary_minutes" not in data.frame.columns


def test_queries_ask_for_the_right_dates(health):
    load_daily(health, START, END)
    field = "daily_resting_heart_rate.date"
    assert health.filters["daily-resting-heart-rate"] == (
        f'{field} >= "2026-07-01" AND {field} < "2026-07-04"'
    )
    # Sleep is filtered in UTC, widened by a day each side to cover every timezone.
    assert '>= "2026-06-30T00:00:00Z"' in health.filters["sleep"]
    assert '< "2026-07-05T00:00:00Z"' in health.filters["sleep"]


def test_value_key_matches_the_api_field_names():
    assert daily._value_key("daily-resting-heart-rate") == "dailyRestingHeartRate"
    assert daily._value_key("sleep") == "sleep"
