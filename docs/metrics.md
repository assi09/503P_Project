# Daily metrics

Every column in the daily table produced by `backend/app/ingest/takeout.py`, where it comes from in
a Google Takeout ("Google Health") export, and how it was checked against what Fitbit reports.

**Fitbit** means the value is one Fitbit itself computes and shows in its app. **Derived** means we
compute it from Fitbit data; derived columns are data-quality signals or convenience features, not
Fitbit metrics.

Paths are relative to `Google Health/`. `PA/` is `Physical Activity_GoogleData/`, `GED/` is
`Global Export Data/`. Intraday values are timestamped in UTC and summed per day in the user's
timezone; daily values are keyed by calendar date.

## Activity

| Column | Unit | Source | Kind | How it is built |
|---|---|---|---|---|
| `steps` | steps | `PA/Steps` | Fitbit | intraday, summed per local day |
| `calories` | kcal | `PA/Calories` | Fitbit | intraday, summed per local day (includes resting burn) |
| `distance_km` | km | `PA/Distance` | Fitbit | intraday meters, summed per local day, / 1000 |
| `active_zone_minutes` | min | `PA/Active Zone Minutes` | Fitbit | intraday, summed; cardio and peak minutes already count 2 in the export; 0 on worn days with no zone minutes |
| `cardio_load` | load | `PA/Cardio Load` | Fitbit | intraday `total` (workout + background), summed per local day |
| `sedentary_minutes` | min | `GED/sedentary_minutes-*.json` | Fitbit | Fitbit's daily total; days with a full 1440 sedentary minutes mean no device data and are dropped |
| `lightly_active_minutes` | min | `GED/lightly_active_minutes-*.json` | Fitbit | Fitbit's daily total |
| `moderately_active_minutes` | min | `GED/moderately_active_minutes-*.json` | Fitbit | Fitbit's daily total |
| `very_active_minutes` | min | `GED/very_active_minutes-*.json` | Fitbit | Fitbit's daily total |
| `wear_minutes` | min | `PA/Activity Level` | Derived | count of minutes with an activity level, which is only recorded while the device is worn and the user is awake |

## Heart and recovery

| Column | Unit | Source | Kind | How it is built |
|---|---|---|---|---|
| `resting_hr` | bpm | `PA/Daily Resting Heart Rate` | Fitbit | daily value |
| `hrv_ms` | ms | `PA/Daily Heart Rate Variability` | Fitbit | daily `average heart rate variability milliseconds` (RMSSD during sleep) |
| `respiratory_rate` | breaths/min | `PA/Daily Respiratory Rate` | Fitbit | daily value during sleep |
| `readiness` | 0-100 | `PA/Daily Readiness` | Fitbit | Daily Readiness score |
| `skin_temp_variation_c` | °C | `PA/Daily Sleep Temperature Derivations` | Fitbit | nightly skin temperature minus personal baseline, as the app shows it; missing until a baseline exists |

## Sleep

From the main sleep log of each night (`GED/sleep-*.json`); naps are ignored and, if a night has
several main sleeps, the longest is used.

| Column | Unit | Kind | How it is built |
|---|---|---|---|
| `sleep_minutes` | min | Fitbit | `minutesAsleep` |
| `time_in_bed` | min | Fitbit | `timeInBed` |
| `sleep_efficiency` | % | Fitbit | `efficiency` |
| `sleep_score` | 0-100 | Fitbit | `overall_score` from `Sleep Score/`, matched to the sleep log by log id |
| `deep_sleep_minutes`, `light_sleep_minutes`, `rem_sleep_minutes`, `awake_in_bed_minutes` | min | Fitbit | stage minutes; missing for "classic" logs, which have no stages |
| `bedtime_hour` | hours | Derived | sleep start relative to midnight (23:30 is -0.5, 01:00 is 1.0) |

## Verification against Fitbit's own daily values

The export also contains Fitbit's legacy per-minute and daily files in `GED/`. On a real export
(111 days, Asia/Beirut), per local day:

| Column | Result |
|---|---|
| `steps` | within 1% on 98% of days |
| `calories` | median difference of a few kcal per day (the legacy file stores calories in local time, steps in UTC) |
| `distance_km` | same daily average as Fitbit's legacy distance (stored there in centimeters) |
| `resting_hr` | within 2 bpm on every day |
| activity minutes | now taken directly from Fitbit's daily totals |

Before this check, activity minutes were counted from the per-minute `Activity Level` labels, which
use a different classification and overstated moderate minutes by about 80%.

## Present in the export but not used

| Data | Reason |
|---|---|
| SpO2 (`Oxygen Saturation (SpO2)/`) | only README files, no data |
| `GED/estimated_oxygen_variation-*.csv` | raw infrared/red signal ratio, not a metric |
| `Stress Score/` | almost every day is `NO_DATA` or requires Premium consent |
| Weight | too few readings to analyze |
| `Biometrics/` (glucose) | medical data, outside the project's scope |
| Profile, account, social and notification files | personal data, never read |
