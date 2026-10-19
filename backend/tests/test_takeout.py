import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from app.ingest.takeout import IngestError, find_export_root, load_daily
from app.synthetic import BASELINES

TZ = "Asia/Beirut"  # UTC+3 in summer
ACTIVITY = "Physical Activity_GoogleData"
# Headers, file names and data source labels below are copied from a real export.
DEVICE = "Google Fitbit Air"
APP = "Google Health App"


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


def sleep_log(date, minutes, start, main=True, kind="stages", deep=80, log_id=0):
    """A sleep log with every field of a real export, in the same order."""
    if kind == "stages":
        summary = {
            stage: {"count": 4, "minutes": value, "thirtyDayAvgMinutes": value}
            for stage, value in (("deep", deep), ("wake", 30), ("light", 200), ("rem", 100))
        }
    else:  # "classic" logs have no sleep stages
        summary = {
            level: {"count": 2, "minutes": value}
            for level, value in (("restless", 10), ("awake", 20), ("asleep", minutes))
        }
    return {
        "logId": log_id,
        "dateOfSleep": date,
        "startTime": start,
        "endTime": start,  # not read
        "duration": (minutes + 30) * 60_000,
        "minutesToFallAsleep": 0,
        "minutesAsleep": minutes,
        "minutesAwake": 30,
        "minutesAfterWakeup": 0,
        "timeInBed": minutes + 30,
        "efficiency": 95,
        "type": kind,
        "infoCode": 0,
        "logType": "auto_detected",
        "levels": {
            "summary": summary,
            "data": [{"dateTime": start, "level": "light", "seconds": 1800}],
            "shortData": [],
        },
        "mainSleep": main,
    }


@pytest.fixture
def export(tmp_path: Path) -> Path:
    write(
        tmp_path,
        f"{ACTIVITY}/Steps/steps_2026-07-01.csv",
        "timestamp,steps,data source\n"
        f"2026-07-01T10:00:00Z,100,{DEVICE}\n"
        f"2026-07-01T20:59:00Z,50,{DEVICE}\n"  # 23:59 local, still Jul 1
        f"2026-07-01T22:30:00Z,7,{DEVICE}\n",  # 01:30 local on Jul 2
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Calories/calories_2026-07-01.csv",
        "timestamp,calories,data source\n"
        f"2026-07-01T10:00:00Z,1.1,{APP}\n"
        f"2026-07-01T10:01:00Z,4.9,{APP}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Distance/distance_2026-07-01.csv",
        "timestamp,distance,data source\n"
        f"2026-07-01T10:00:00Z,750.5,{DEVICE}\n"
        f"2026-07-01T10:01:00Z,249.5,{DEVICE}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Cardio Load/cardio_load_2026-07-01.csv",
        "timestamp,workout,background,total,data source\n"
        f"2026-07-01T10:00:00Z,2.0,0.5,2.5,{DEVICE}\n"
        f"2026-07-01T10:01:00Z,0.0,0.5,0.5,{DEVICE}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Resting Heart Rate/daily_resting_heart_rate.csv",
        "timestamp,beats per minute,data source\n"
        f"2026-07-01T00:00:00Z,60.5,{APP}\n"
        f"2026-07-03T00:00:00Z,62.0,{APP}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Heart Rate Variability/daily_heart_rate_variability.csv",
        "timestamp,average heart rate variability milliseconds,non rem heart rate beats per minute,"
        "entropy,deep sleep root mean square of successive differences milliseconds,data source\n"
        f"2026-07-02T00:00:00Z,52.3,58.0,3.1,48.2,{APP}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Respiratory Rate/daily_respiratory_rate.csv",
        f"timestamp,breaths per minute,data source\n2026-07-02T00:00:00Z,14.6,{APP}\n",
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Readiness/daily_readiness.csv",
        "timestamp,score,type,readiness level,sleep readiness,heart rate variability readiness,"
        "resting heart rate readiness,data source\n"
        f"2026-07-03,72,MEDIUM,TYPE_UNSPECIFIED,HIGH,MEDIUM,LOW,{APP}\n",  # date only
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Activity Level/activity_level_2026-07-01.csv",
        "timestamp,level,data source\n"
        f"2026-07-01T10:00:00Z,SEDENTARY,{APP}\n"
        f"2026-07-01T10:01:00Z,SEDENTARY,{APP}\n"
        f"2026-07-01T10:02:00Z,VERY_ACTIVE,{APP}\n"
        f"2026-07-01T22:30:00Z,SEDENTARY,{APP}\n",  # 01:30 local on Jul 2
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Active Zone Minutes/active_zone_minutes_2026-07-01.csv",
        "timestamp,heart rate zone,total minutes,data source\n"
        f"2026-07-01T10:00:00Z,FAT_BURN,1,{DEVICE}\n"
        f"2026-07-01T10:01:00Z,PEAK,2,{DEVICE}\n",
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
        sleep_log("2026-07-02", 420, "2026-07-01T23:30:00.000", log_id=101),
        sleep_log("2026-07-02", 60, "2026-07-02T15:00:00.000", main=False),  # nap
        sleep_log("2026-07-03", 200, "2026-07-03T01:00:00.000", deep=40),
        sleep_log("2026-07-03", 300, "2026-07-03T05:00:00.000", kind="classic"),
    ]
    write(tmp_path, "Global Export Data/sleep-2026-07-01.json", json.dumps(logs))
    write(
        tmp_path,
        "Sleep Score/sleep_score.csv",
        "sleep_log_entry_id,timestamp,overall_score,composition_score,revitalization_score,"
        "duration_score,deep_sleep_in_minutes,resting_heart_rate,restlessness\n"
        "101,2026-07-02T06:30:00Z,82,,82,,80,60,0.081\n"
        "999,2026-07-03T06:30:00Z,50,,50,,40,61,0.093\n",  # belongs to no exported sleep log
    )
    write(
        tmp_path,
        f"{ACTIVITY}/Daily Sleep Temperature Derivations/daily_sleep_temperature_derivations.csv",
        "timestamp,nightly temperature celsius,baseline temperature celsius,"
        "relative nightly stddev 30d celsius,data source\n"
        f"2026-07-01T00:00:00Z,32.5,NaN,NaN,{APP}\n"  # no baseline yet in the first nights
        f"2026-07-02T00:00:00Z,33.0,32.6,0.5,{APP}\n",
    )
    return tmp_path


def day(frame: pd.DataFrame, date: str) -> pd.Series:
    return frame.loc[pd.Timestamp(date)]


def test_intraday_values_are_bucketed_by_local_day(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-01")["steps"] == 150
    assert day(frame, "2026-07-02")["steps"] == 7


def test_calories_are_summed_per_local_day(export):
    assert day(load_daily(export, TZ).frame, "2026-07-01")["calories"] == pytest.approx(6.0)


def test_sleep_time_daily_metrics_are_read(export):
    row = day(load_daily(export, TZ).frame, "2026-07-02")
    assert row["hrv_ms"] == 52.3
    assert row["respiratory_rate"] == 14.6


def test_readiness_with_date_only_timestamps(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-03")["readiness"] == 72
    assert pd.isna(day(frame, "2026-07-02")["readiness"])


def test_distance_is_converted_to_kilometers(export):
    assert day(load_daily(export, TZ).frame, "2026-07-01")["distance_km"] == 1.0


def test_cardio_load_sums_workout_and_background_load(export):
    assert day(load_daily(export, TZ).frame, "2026-07-01")["cardio_load"] == 3.0


def test_zone_minutes_are_zero_on_worn_days_without_zones(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-01")["active_zone_minutes"] == 3
    assert day(frame, "2026-07-02")["active_zone_minutes"] == 0
    assert pd.isna(day(frame, "2026-07-03")["active_zone_minutes"])  # not worn


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


def test_sleep_score_is_matched_to_its_sleep_log(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-02")["sleep_score"] == 82
    assert pd.isna(day(frame, "2026-07-03")["sleep_score"])


def test_skin_temperature_is_relative_to_personal_baseline(export):
    frame = load_daily(export, TZ).frame
    assert day(frame, "2026-07-02")["skin_temp_variation_c"] == 0.4
    assert pd.isna(day(frame, "2026-07-01")["skin_temp_variation_c"])


def test_synthetic_data_covers_every_ingested_column(export):
    columns = list(load_daily(export, TZ).frame.columns)
    assert [name for name in BASELINES if name in columns] == columns


def test_full_export_reports_nothing_missing(export):
    assert load_daily(export, TZ).missing == []


def test_missing_metrics_are_reported(export):
    shutil.rmtree(export / "Takeout" / "Google Health" / ACTIVITY / "Daily Heart Rate Variability")
    data = load_daily(export, TZ)
    assert data.missing == ["hrv_ms"]
    assert "hrv_ms" not in data.frame.columns


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
