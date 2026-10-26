# Strain and stress scores (proposed)

Two new daily scores, our own and deterministic like the [recovery score](product.md#recovery-score):
**strain** (how much load the heart carried today) and **stress** (how many physical signs of
stress the body showed). Both are needed for the [team view](teams.md), and both are useful to the
person on Today. Status: researched, not built. The formulas below are the starting point; the
numbers in them are to be checked on synthetic data and on our own before they are fixed.

Like every score in the app, they describe the person's own data against their own baseline.
They are not medical measurements, and "stress" means physiological signs only, never a mental
state or a diagnosis.

## What others do

| Product | Strain / load | Stress |
|---|---|---|
| WHOOP | 0-21, from heart rate (how high and how long, relative to the person's own max) plus muscular load; the exact formula is not published, the scale is bounded and grows slower near the top | — |
| Garmin (Firstbeat) | training load from heart rate | 0-100 from beat-to-beat HRV against the person's baseline |
| Oura | — | daytime stress from HRV, heart rate, motion and skin temperature, only while awake and still, against personal baselines |
| Fitbit | Active Zone Minutes, cardio load | Stress Management Score 1-100: heart rate and HRV, EDA where available, exertion balance, sleep |
| Research | Banister's and Edwards' TRIMP: time at each heart-rate intensity times a weight. The two agree closely in most studies; weaker for stop-and-go sports, and both depend on a good maximum heart rate | Daytime HRV and heart rate above what movement explains are the common signals |

What we can read: minute-level `heart-rate` samples (already read for workouts), daily resting
heart rate, nightly HRV (RMSSD), Active Zone Minutes, steps, sleep. We cannot read EDA or daytime
HRV, and Fitbit's own stress score is not in the API (in Takeout it is almost always `NO_DATA`).

## Strain (`strain_v1`), 0 to 21

A mix of the two approaches: heart-rate zones when the minute samples are there, Active Zone
Minutes when they are not.

1. **Zones from heart-rate reserve.** For each minute with a sample:
   `reserve = (HR - resting) / (HRmax - resting)`, using that day's resting heart rate. Zones as in
   Edwards' TRIMP: 50-60% weight 1, 60-70% weight 2, 70-80% weight 3, 80-90% weight 4, 90%+
   weight 5; below 50% counts nothing. Load = the sum of weighted minutes (Edwards' TRIMP, on
   reserve rather than %HRmax so a high resting heart rate is not counted as effort).
2. **Fallback.** On a day without minute samples, load is estimated from Active Zone Minutes, which
   Fitbit also counts from heart-rate reserve zones. The scaling between the two is fitted on days
   that have both. The day records which method was used.
3. **Bounded scale.** `strain = 21 × (1 − exp(−load / k))`, so each extra minute adds less near the
   top, as with WHOOP. `k` is set so a typical hard workout day lands around 14 (WHOOP's "high").
   The bands are 0-9 light, 10-13 moderate, 14-17 high and 18-21 all out.
4. **Maximum heart rate** is the open question (see below). Until it is settled, use the highest
   sustained heart rate the person reached in the last 90 days (the 99.5th percentile of minute
   samples, so a single bad reading does not count).

Checks: on synthetic days with planted workouts, strain increases with duration and intensity
and never passes 21; the AZM fallback agrees with the zone method on days that have both.

## Stress (`stress_v1`), 0 to 100, higher means more signs of stress

Recovery already covers the overnight signals. To avoid scoring the same thing twice, stress is
weighted toward **daytime**:

1. **Stationary heart-rate load (most weight).** These are minutes while awake (outside the sleep
   session) with at most a few steps that minute and the minutes around it, and a heart rate more
   than a set margin above that day's resting rate. The score uses the share of such still minutes
   with an elevated heart rate. This is the movement-adjusted heart rate behind Oura's and
   Fitbit's responsiveness signals, without EDA or daytime HRV.
2. **Nightly HRV below baseline and resting heart rate above it** (less weight, shared with
   recovery).
3. **Sleep shortfall** against the person's usual (least weight).

Each input becomes a robust z-score against the person's previous 28-60 days, as for recovery. The
inputs are combined with fixed, versioned weights and mapped to 0-100, where 50 is a typical day.
There is no score on days with too little wear while awake, and none before there is a baseline.

**Ground truth.** Nothing we can read measures stress directly, so the score is checked against
the person: an optional evening check-in ("how stressful was today?", 1-5) beside the morning one.
The evaluation reports the rank correlation between the score and those ratings, as a pilot with
one or two people.

## Storage

Minute samples are not stored. At each sync, a day's minute samples are reduced to a few daily
inputs, saved as ordinary daily metrics from the same source:

- `hr_zone_load` (and the minutes in each zone)
- `still_elevated_share`
- `strain`
- `stress`

This keeps the one-source rule, and the analysis tools and the agent can use the inputs like any
other metric. Reading minute heart rate for every day of the history is many API calls, so the
first sync computes it for recent days first, as with everything else.

## Open

- **Maximum heart rate:** observed (above), or from age (Tanaka: 208 − 0.7 × age), which would
  mean asking for an age. Observed max underestimates for someone who never trains hard.
- The margin and step threshold for "still and elevated", to be tuned on our own data.
- Whether strain should add a muscular part for strength workouts, as WHOOP now does. Heart rate
  alone undercounts lifting.
