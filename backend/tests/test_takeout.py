import json
from pathlib import Path

import pandas as pd
import pytest

from app.ingest.takeout import IngestError, find_export_root, load_daily

TZ = "Asia/Beirut"  # UTC+3 in summer
ACTIVITY = "Physical Activity_GoogleData"


def write(root: Path, relpath: str, content: str) -> None:
    path = root / "Takeout" / "Google Health" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def daily_totals(values: dict[str, float]) -> str:
    return json.dumps(
        [
            {"dateTime": f"{d[5:7]}/{d[8:10]}/{d[2:4]} 00:00:00", "value": str(v)}
            for d, v in values.items()
        ]
    )


def sleep_log(date, minutes, start, main=True, kind="stages", deep=80):
    log = {
        "dateOfSleep": date,
        "startTime": start,
        "minutesAsleep": minutes,
        "timeInBed": minutes + 30,
        "efficiency": 95,
        "mainSleep": main,
        "type": kind,
        "levels": {"summary": {}},
    }
    if kind == "stages":
        log["levels"]["summary"] = {
            "deep": {"minutes": deep},
            "light": {"minutes": 200},
            "rem": {"minutes": 100},
            "wake": {"minutes": 30},
        }
    return log


@pytest.fixture
def export(tmp_path: Path) -> Path:
    write(
        tmp_path,
        f"{ACTIVITY}/Steps/steps_2026-07-01.csv",
        "timestamp,steps,data source\n"
        "2026-07-01T10:00:00Z,100,Device\n"
        "2026-07-01T20:59:00Z,50,Device\n"  # 23:59 local, still Jul 1
        "2026-07-01T22:30:00Z,7,Device\n",  # 01:30 local on Jul 2
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Distance/distance_2026-07-01.csv",
        "timestamp,distance,data source\n"
        "2026-07-01T10:00:00Z,750.5,Device\n"
        "2026-07-01T10:01:00Z,249.5,Device\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Cardio Load/cardio_load_2026-07-01.csv",
        "timestamp,workout,background,total,data source\n"
        "2026-07-01T10:00:00Z,2.0,0.5,2.5,Device\n"
        "2026-07-01T10:01:00Z,0.0,0.5,0.5,Device\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Resting Heart Rate/daily_resting_heart_rate.csv",
        "timestamp,beats per minute,data source\n"
        "2026-07-01T00:00:00Z,60.5,App\n"
        "2026-07-03T00:00:00Z,62.0,App\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Activity Level/activity_level_2026-07-01.csv",
        "timestamp,level,data source\n"
        "2026-07-01T10:00:00Z,SEDENTARY,App\n"
        "2026-07-01T10:01:00Z,SEDENTARY,App\n"
        "2026-07-01T10:02:00Z,VERY_ACTIVE,App\n",
    )
    totals = {
        "sedentary_minutes": {"2026-06-30": 1440, "2026-07-01": 600},
        "lightly_active_minutes": {"2026-06-30": 0, "2026-07-01": 200},
        "moderately_active_minutes": {"2026-06-30": 0, "2026-07-01": 30},
        "very_active_minutes": {"2026-06-30": 0, "2026-07-01": 15},
    }
    for name, values in totals.items():
        write(tmp_path, f"Global Export Data/{name}-2026-06-30.json", daily_totals(values))
    logs = [
        sleep_log("2026-07-02", 420, "2026-07-01T23:30:00.000"),
        sleep_log("2026-07-02", 60, "2026-07-02T15:00:00.000", main=False),  # nap
        sleep_log("2026-07-03", 200, "2026-07-03T01:00:00.000", deep=40),
        sleep_log("2026-07-03", 300, "2026-07-03T05:00:00.000", kind="classic"),
    ]
    write(tmp_path, "Global Export Data/sleep-2026-07-01.json", json.dumps(logs))
    return tmp_path


def day(frame: pd.DataFrame, date: str) -> pd.Series:
    return frame.loc[pd.Timestamp(date)]


def test_intraday_values_are_bucketed_by_local_day(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-01")["steps"] == 150
    assert day(frame, "2026-07-02")["steps"] == 7


def test_distance_is_converted_to_kilometers(export):
    assert day(load_daily(export, TZ).frame, "2026-07-01")["distance_km"] == 1.0


def test_cardio_load_sums_workout_and_background_load(export):
    assert day(load_daily(export, TZ).frame, "2026-07-01")["cardio_load"] == 3.0


def test_daily_values_keep_their_calendar_date(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-01")["resting_hr"] == 60.5
    assert day(frame, "2026-07-03")["resting_hr"] == 62.0


def test_gaps_are_filled_with_missing_rows(export):
    frame = load_daily(export, TZ).frame
    assert list(frame.index.strftime("%m-%d")) == ["07-01", "07-02", "07-03"]
    assert pd.isna(day(frame, "2026-07-02")["resting_hr"])


def test_activity_minutes_come_from_fitbit_daily_totals(export):
    row = day(load_daily(export, TZ).frame, "2026-07-01")
    assert row["sedentary_minutes"] == 600
    assert row["lightly_active_minutes"] == 200
    assert row["moderately_active_minutes"] == 30
    assert row["very_active_minutes"] == 15


def test_days_without_device_data_are_dropped_not_counted_as_sedentary(export):
    frame = load_daily(export, TZ).frame
    assert frame.index[0] == pd.Timestamp("2026-07-01")


def test_wear_time_counts_recorded_activity_level_minutes(export):
    row = day(load_daily(export, TZ).frame, "2026-07-01")
    assert row["wear_minutes"] == 3


def test_main_sleep_ignores_naps(export):
    row = day(load_daily(export, TZ).frame, "2026-07-02")
    assert row["sleep_minutes"] == 420
    assert row["deep_sleep_minutes"] == 80
    assert row["bedtime_hour"] == -0.5  # 23:30 is half an hour before midnight


def test_longest_main_sleep_wins_and_classic_logs_have_no_stages(export):
    row = day(load_daily(export, TZ).frame, "2026-07-03")
    assert row["sleep_minutes"] == 300
    assert row["bedtime_hour"] == 5.0
    assert pd.isna(row["deep_sleep_minutes"])


def test_missing_metrics_are_reported(export):
    missing = load_daily(export, TZ).missing
    assert "hrv_ms" in missing
    assert "steps" not in missing
    assert "sleep" not in missing


def test_export_root_can_be_given_at_any_level(export):
    expected = export / "Takeout" / "Google Health"
    assert find_export_root(export) == expected
    assert find_export_root(export / "Takeout") == expected
    assert find_export_root(expected) == expected


def test_folder_without_export_is_rejected(tmp_path):
    with pytest.raises(IngestError, match="No 'Google Health' folder"):
        load_daily(tmp_path, TZ)


def test_export_without_supported_metrics_is_rejected(tmp_path):
    write(tmp_path, "Your Profile/Profile.csv", "id\n1\n")
    with pytest.raises(IngestError, match="none of the supported metrics"):
        load_daily(tmp_path, TZ)


def test_csv_with_missing_columns_is_rejected(tmp_path):
    write(tmp_path, f"{ACTIVITY}/Steps/steps.csv", "timestamp,count\n2026-07-01T10:00:00Z,5\n")
    with pytest.raises(IngestError, match="missing columns"):
        load_daily(tmp_path, TZ)


def test_unparseable_timestamps_are_rejected(tmp_path):
    write(tmp_path, f"{ACTIVITY}/Steps/steps.csv", "timestamp,steps\nyesterday,5\n")
    with pytest.raises(IngestError, match="unparseable timestamps"):
        load_daily(tmp_path, TZ)


def test_malformed_daily_total_is_rejected(tmp_path):
    entry = json.dumps([{"dateTime": "yesterday", "value": "5"}])
    write(tmp_path, "Global Export Data/sedentary_minutes-2026-07-01.json", entry)
    with pytest.raises(IngestError, match="Malformed entry"):
        load_daily(tmp_path, TZ)


def test_corrupt_sleep_json_is_rejected(tmp_path):
    write(tmp_path, "Global Export Data/sleep-2026-07-01.json", "[{not json")
    with pytest.raises(IngestError, match="Unreadable file"):
        load_daily(tmp_path, TZ)


def test_sleep_log_missing_fields_is_rejected(tmp_path):
    write(tmp_path, "Global Export Data/sleep-2026-07-01.json", json.dumps([{"mainSleep": True}]))
    with pytest.raises(IngestError, match="Malformed sleep log"):
        load_daily(tmp_path, TZ)
