# Strain and stress scores (proposed)

Two new daily scores, our own and deterministic like the [recovery score](product.md#recovery-score):
**strain** (how much load the heart carried today) and **stress** (how many physical signs of
stress the body showed). Every person sees them on Today. A supervisor sees their weekly levels
only for people who opted in ([teams.md](teams.md)). Status: researched and checked against the
API, not built. The constants below are starting points, to be checked on synthetic data and on
our own before they are fixed.

Like every score in the app, they describe the person's own data against their own baseline.
They are not medical measurements. "Stress" means physical signs only, never a mental state or a
diagnosis.

## What others do

| Product | Strain / load | Stress |
|---|---|---|
| WHOOP | 0-21, from heart rate (how high and how long, relative to the person's own max) plus muscular load; the exact formula is not published, the scale is bounded and grows slower near the top | — |
| Garmin (Firstbeat) | training load from heart rate | 0-100 from beat-to-beat HRV against the person's baseline |
| Oura | — | daytime stress from HRV, heart rate, motion and skin temperature, only while awake and still, against personal baselines |
| Fitbit | Active Zone Minutes, cardio load | Stress Management Score 1-100: heart rate and HRV, EDA where available, exertion balance, sleep |
| Research | Banister's and Edwards' TRIMP: time at each heart-rate intensity times a weight. The two agree closely in most studies; weaker for stop-and-go sports, and both depend on a good maximum heart rate | Daytime HRV and heart rate above what movement explains are the common signals |

## What the API gives us (checked 2026-10-26)

A read-only check on 7 days of the owner's account, recording only counts, timings and field
names:

| Data type | Request | Result | Use |
|---|---|---|---|
| `time-in-heart-rate-zone` | daily roll-up | one point per day with seconds in `LIGHT`, `MODERATE`, `VIGOROUS` (and `PEAK` when reached); 7 days in 1.6 s, 14 days per request | strain |
| `heart-rate` | roll-up in 60 s windows | about 1,440 points per day (average, min, max), **one request per day**, 1.4 s | stress |
| `heart-rate` | list of samples | 38,550 samples for one day, 5.5 s | not used: too heavy |
| `activity-level` | list | about 900 intervals a day, each with `activityLevelType`; recorded only while worn and awake (already read for wear time) | stress: awake and still |

We cannot read EDA, daytime HRV or Fitbit's own stress score (in Takeout that is almost always
`NO_DATA`).

## Strain (`strain_v1`), 0 to 21

1. **Load from Fitbit's own heart-rate zones.** Fitbit sets these zones from heart-rate reserve,
   using the wearer's resting heart rate and age. So the daily zone roll-up already reflects how
   hard the effort was for this person, which settles the maximum-heart-rate question without
   asking anyone's age. Load is the minutes in each zone times a weight, as in Edwards' TRIMP:
   `LIGHT` 1, `MODERATE` 2, `VIGOROUS` 3, `PEAK` 4.
2. **Bounded scale.** `strain = 21 × (1 − exp(−load / k))`, so each extra minute adds less near the
   top, as with WHOOP. `k` is set so that a typical workout day lands around 14, WHOOP's "high".
   Bands: 0-9 light, 10-13 moderate, 14-17 high, 18-21 all out.
3. **No zones that day** (not worn, or nothing above the light zone): Active Zone Minutes, from
   the same zones, gives the fallback; with neither there is no strain, not a zero.
4. **Later (`strain_v2`):** a muscular part for strength workouts, from logged
   strength-training minutes, since heart rate undercounts lifting.

Checks: strain increases with zone minutes and intensity, never passes 21, and is 0 with no zone
time. On synthetic days with planted workouts it rises on those days; the fallback agrees with
the zone method on days that have both.

## Stress (`stress_v1`), 0 to 100, higher means more signs of stress

Recovery already covers the overnight signals. To avoid scoring the same thing twice, stress is
weighted toward **daytime**:

1. **Still-elevated minutes (60% of the weight).** These are awake minutes where the activity
   level is sedentary, at least 10 minutes after the last active minute (so the heart rate coming
   down after exercise is not counted), and the minute's heart rate is above that day's resting
   rate by more than a margin. The margin starts at the larger of 10 bpm and the spread of the
   person's own still heart rate over the previous 28 days. The input is the share of still
   minutes that are elevated. This is the movement-adjusted heart rate behind Oura's and Fitbit's
   responsiveness signals, without EDA.
2. **Nightly HRV below the person's usual and resting heart rate above it (25%),** shared with
   recovery.
3. **Sleep shortfall against the person's usual (15%).**

Each input becomes a robust z-score against the person's previous 28-60 days, as for recovery.
They are combined with the fixed weights above, versioned in code, and mapped to 0-100, where 50
is a typical day for this person. There is no score with fewer than 4 hours of still, awake wear
that day, or before there is a baseline. Each score lists its parts, so the app and the agent
can explain it.

**Ground truth.** Nothing we can read measures stress directly, so the score is checked against
the person: an optional evening check-in ("how stressful was today?", 1-5) next to the morning
one. The evaluation reports the rank correlation between the score and those ratings, as a pilot
with one or two people. A still-elevated minute also means caffeine, heat, illness or a standing
desk, and the score's explanation says so.

## Storage and computation

The same as recovery: the sync stores the **inputs** as ordinary daily metrics from the same
source, and the scores are computed from them when read. A new formula version therefore never
needs a resync.

- `hr_zone_light_minutes`, `hr_zone_moderate_minutes`, `hr_zone_vigorous_minutes`,
  `hr_zone_peak_minutes`: from the zone roll-up, cheap for the whole history.
- `still_minutes` and `still_elevated_minutes`: from the minute heart-rate roll-up and the
  activity-level intervals, one extra request per day. The first sync fills recent days first, as
  it already does, and syncs after that reread the last 3 days.
- `strain` and `stress` are computed in `backend/app/analysis/` next to recovery (`day.py`).
  `/days/{date}` returns them with their parts, like `recovery`. They join the metric list, so the
  metric pages, the screen, the evidence pages and the experts use them like any other metric
  (strain belongs to the activity expert, stress to recovery).

Minute heart rate is never stored, only the two daily counts.

## On Today

- **Key numbers become Recovery, Strain, Sleep and Stress**: a 2×2 grid on phones, one row on
  wide screens. Each is shown in large type against the usual range, and opens its metric page.
  Steps moves to the top of the Activity section. Resting heart rate stays in Heart and body.
- Strain shows its band (light, moderate, high, all out). Stress shows "below usual", "usual" or
  "above usual" rather than a bare number, since 50 means a typical day.
- The metric pages explain the inputs: zone minutes for strain; still-elevated time, HRV, resting
  heart rate and sleep for stress. The evening stress check-in is a row beside the morning one.
- Light and dark mode, flat rows as in the [UI plan](ui-plan.md).

## Open

- The constants: `k` for strain, and the margin and the 10-minute gap for stress, tuned on our
  own data before they are fixed.
- Whether stress also uses skin temperature, as Oura does. It is nightly only in the API.
