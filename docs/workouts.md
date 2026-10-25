# Workout logging: types, metrics and mappings

How a workout the agent logs is built, which Google fields it fills, where each value comes from,
and how each choice was checked. The code is `backend/app/actions/exercises.py` (types and kinds),
`measure.py` (reading the tracker) and `schemas.py` (the payload sent to Google). The flow around it
(drafts, review, confirmation, undo) is in [agent-actions.md](agent-actions.md) and
[architecture.md](architecture.md#confirmed-action-execution).

## The flow in one paragraph

The person says what they did ("45 minutes of kickboxing yesterday at 6pm"). The Activity expert
calls `propose_workout_log` with the type, start, end, active time and any distance the person
gave; it never supplies measurements. The server validates it, reads what the tracker recorded over
that interval (below) and stores the draft with that reading as `measured`. The app shows the
card; nothing reaches Google until the person presses *Log it*. Saving the draft again (an edit,
or *Refresh from Fitbit*) reads the tracker again.

## Types

Drafts accept all 181 of Google's `Exercise.ExerciseType` values except `EXERCISE_TYPE_UNSPECIFIED`
(`PICKELBALL` is Google's spelling). The agent picks the closest one; `OTHER` only if nothing fits.
The name sent to Google (`displayName`, required) is Fitbit's where known ("Run", "Walk") and
otherwise the type in plain words ("Kickboxing"); the app shows the same names.

## Kinds: which metrics a workout gets

Every type belongs to one kind. The kinds follow what Fitbit itself put in the summaries of the
119 workouts it recorded for the owner (12 types); types the owner has not done are placed by the
same rule and are **not verified on real data**.

| Kind | From the tracker | Verified on the owner's workouts |
|---|---|---|
| Every workout, when worn | total calories, average heart rate, seconds in each heart-rate zone, Active Zone Minutes (left out when 0) | all 12 types |
| On foot | + steps, distance, pace | `WALKING` (42) |
| Court and field sports | + steps, distance (no pace) | `SOCCER`, `TENNIS`, `VOLLEYBALL`, `SPORT` |
| Step-based | + steps (distance from stride means nothing on a machine) | `ELLIPTICAL` |
| Swimming | + pool lengths | none |
| Everything else | heart-based only | `WEIGHTLIFTING`, `STRENGTH_TRAINING`, `CARDIO_WORKOUT`, `WORKOUT` |

**On foot** (16): `BACKPACKING`, `HIKING`, `INCLINE_RUN`, `INCLINE_WALK`, `NORDIC_WALKING`, `ORIENTEERING`, `POWER_WALKING`, `RUCKING`, `RUNNING`, `SNOWSHOEING`, `STROLLER_WALK`, `TRAIL_RUN`, `TREADMILL`, `TREADMILL_WALK`, `WALKING`, `WALK_WITH_WEIGHTS`

**Court and field sports** (27): `BADMINTON`, `BASEBALL`, `BASKETBALL`, `CHEERLEADING`, `CRICKET`, `FIELD_HOCKEY`, `FOOTBALL_AMERICAN`, `FOOTBALL_AUSTRALIAN`, `FRISBEE_PLAYING_GENERAL`, `GOLF`, `HANDBALL`, `LACROSSE`, `PADEL`, `PICKELBALL`, `RACKET_SPORTS`, `RACQUETBALL`, `RUGBY`, `SOCCER`, `SOFTBALL`, `SPORT`, `SQUASH`, `TABLE_TENNIS`, `TENNIS`, `TRACK_AND_FIELD`, `ULTIMATE_FRISBEE`, `VOLLEYBALL`, `VOLLEYBALL_BEACH`

**Step-based** (14): `BALLET`, `BALLROOM_DANCE`, `BARRE_CLASS`, `BREAKDANCING`, `DANCING`, `ELLIPTICAL`, `HIP_HOP`, `JAZZ_DANCE`, `JUMPING_ROPE`, `MODERN_DANCE`, `STAIRCLIMBER`, `STEP_TRAINING`, `TANGO`, `ZUMBA`

**Swimming** (3): `SWIMMING`, `SWIMMING_OPEN_WATER`, `SWIMMING_POOL`

**Everything else** (121): `AEROBIC_WORKOUT`, `ARCHERY`, `ASSAULT_BIKE`, `BIKING`, `BILLIARDS`, `BODY_WEIGHT`, `BOOTCAMP`, `BOWLING`, `BOXING`, `CALISTHENICS`, `CANOEING`, `CARDIO_SCULPT`, `CARDIO_WORKOUT`, `CARPENTRY`, `CIRCUIT_TRAINING`, `CLEANING`, `CLIMBING`, `CORE_TRAINING`, `CROQUET`, `CROSS_COUNTRY_SKI`, `CROSS_TRAINING`, `CROSSFIT`, `CURLING`, `DIVING`, `ELECTRIC_BIKE`, `ELECTRIC_SCOOTER`, `EQUESTRIAN_SPORTS`, `EXERCISE_CLASS`, `FENCING`, `FISHING`, `FITNESS_GAMING`, `FOILING`, `FREE_WEIGHTS`, `FUNCTIONAL_STRENGTH_TRAINING`, `GARDENING`, `GYMNASTICS`, `HAND_CYCLING`, `HIIT`, `HOCKEY`, `HOEING`, `HOUSEHOLD_CHORES`, `HUNTING`, `ICE_SKATING`, `INDOOR_CLIMBING`, `INTERVAL_WORKOUT`, `JIU_JITSU`, `KARATE`, `KAYAKING`, `KICKBOXING`, `KITESURFING`, `MARTIAL_ARTS`, `MEDITATE`, `MOTOCROSS`, `MOTORCYCLE`, `MOUNTAIN_BIKE`, `MOWING_LAWN`, `MUAY_THAI`, `MULTISPORT`, `MUSICAL_PERFORMANCE`, `OTHER`, `OUTDOOR_BIKE`, `OUTDOOR_WORKOUT`, `PADDLEBOARDING`, `PAINTING`, `PARAGLIDING`, `PARKOUR`, `PILATES`, `POLO`, `POWERLIFTING`, `RESISTANCE_BANDS`, `ROCK_CLIMBING`, `ROLLERBLADING`, `ROLLER_SKATING`, `ROWING`, `ROWING_MACHINE`, `SAILING`, `SCOOTERING`, `SCUBA_DIVING`, `SHOOTING`, `SHOVELING`, `SKATEBOARDING`, `SKATING`, `SKIING`, `SKYDIVING`, `SNORKELING`, `SNOWBOARDING`, `SNOWMOBILING`, `SNOW_SPORT`, `SPEED_SKATING`, `SPINNING`, `STATIONARY_BIKE`, `STRENGTH_TRAINING`, `STRETCHING`, `SURFING`, `SYNCHRONIZED_SWIMMING`, `TABATA_WORKOUT`, `TAEKWONDO`, `TAI_CHI`, `TRAMPOLINE`, `TRX`, `UNICYCLING`, `WAKEBOARDING`, `WATER_AEROBICS`, `WATER_JOGGING`, `WATER_POLO`, `WATER_SKIING`, `WATER_SPORT`, `WATER_VOLLEYBALL`, `WEEDING`, `WEIGHTLIFTING`, `WEIGHT_MACHINES`, `WEIGHTS`, `WHEELCHAIR`, `WINDSURFING`, `WORKOUT`, `WRESTLING`, `YOGA`, `YOGA_BIKRAM`, `YOGA_HATHA`, `YOGA_POWER`, `YOGA_VINYASA`

Distance for cycling, rowing, skating and swimming is never taken from the tracker: its distance
comes from steps and stride, which would be wrong there. Those take only a distance the person gives.

## From the tracker to Google's fields

| Google field (`exercise.metricsSummary`) | Read from | Notes |
|---|---|---|
| `caloriesKcal` | `total-calories` roll-up | total, not active: active was 30-50% below Fitbit's |
| `averageHeartRateBeatsPerMinute` | `heart-rate` roll-up, `beatsPerMinuteAvg` | int64 as a string |
| `heartRateZoneDurations` | `time-in-heart-rate-zone` roll-up | `LIGHT`/`MODERATE`/`VIGOROUS`/`PEAK` -> `lightTime`... as `"600s"` |
| `activeZoneMinutes` | `active-zone-minutes` roll-up | plain sum of the fat-burn, cardio and peak sums (cardio and peak already count double) |
| `steps` | `steps` roll-up, `countSum` | on foot, field and step-based kinds |
| `distanceMillimeters` | the person's distance, else `distance` roll-up | tracker distance only on foot and field kinds |
| `averagePaceSecondsPerMeter` | active seconds / metres | on foot only; Google recomputes it and stores the same value |
| `averageSpeedMillimetersPerSecond` | metres / active seconds | only with a distance, not on foot or field kinds |
| `totalSwimLengths` | count of `swim-lengths-data` points in the interval | swims only: stray "lengths" appear outside the water |

Also sent: `exerciseType`, `displayName`, `interval` (with UTC offsets) and `activeDuration`.
`displayName` and `metricsSummary` are **required** by Google even when empty (PR #57; an empty
`metricsSummary` is accepted). Not sent: minute-level data (the tracker already wrote it, and a
summary does not change daily totals, so nothing is counted twice), `dataSource`, splits, events,
elevation and GPS.

**Rules.** The person's values win; the tracker fills in the rest. No heart rate in the interval
means the tracker was not worn or has not synced: the draft is marked *no data* and only the given
values are sent (total calories exist even then, estimated from resting burn, so none are sent).
Any Google error marks it *unavailable*, and the draft is kept. Speed limits per kind (run 25 km/h,
other on-foot 10, wheels 80, swim 10, paddle 25, skate 60) catch typos in a given distance.

**Overlaps.** Exercises already recorded over the interval (by the tracker or another app) are
listed on the card as a warning, not a refusal: logging would add a second workout, but the
tracker may have the wrong type. Decided with the user, as were "the person's values win" and
"no data logs only the given values".

## Reading the tracker: API details

- Range roll-ups: `POST .../dataTypes/<type>/dataPoints:rollUp` with
  `{"range": {"startTime", "endTime"}, "windowSize": "86400s"}` gives one total for any range up
  to a day (`HealthClient.rollup`).
- Exercises are listed with a filter on `exercise.interval.civil_start_time` in **local time
  without an offset** (`"2026-10-25T13:00:00"`); other field names are refused.
- `total-calories` cannot be listed, only rolled up; `floors` likewise. The swim-lengths roll-up
  only sums strokes, so lengths are counted from the listed points.
- A workout draft costs about 6 to 8 Google reads (no model cost).

## How it was checked

All free reads of the owner's data; only agreement rates were printed. Details in
[experiments.md](experiments.md#every-workout-type-with-fitbits-metrics-for-its-kind-2026-10-25).

- Rolling up each of 119 tracked workouts over its own interval matched Fitbit's summary: steps
  and distance within 2% on all, zones exact on almost all of 113, heart rate within 2% on 118 of
  119, calories within 2% on 101 of 113, Active Zone Minutes exact on 78 of 79.
- Logging each of those workouts again in simulation matched Fitbit's summary field by field,
  except calories on gym sessions with pauses (Fitbit leaves paused time out; a logged workout has
  no pauses).
- Real writes: a walk without a distance (PR #57) and a measured walk (PR #58) were created, read
  back from Google and, for the first, undone.
- Real agent runs: "kickboxing yesterday at 6pm" gave a `KICKBOXING` draft and "tennis this morning
  at 9" a `TENNIS` draft, at the right local times.

## Open

- Types the owner has never done, swims above all, are placed by rule.
- Fitbit labels our writes "Cronometer" ([status.md](status.md#open-issues), issue 22).
- Elevation gain, splits, GPS routes and pauses are not supported.
