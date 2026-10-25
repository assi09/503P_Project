# Product design

What the app does for its user and the decisions behind it. [architecture.md](architecture.md)
covers how it is built. Sections marked *open* are not decided yet.

## User and problem

The user wears a Fitbit (Fitbit Air) and has months of data. The Fitbit app shows daily scores and
simple charts, but answering *"why was my recovery low this week?"* or *"did training more change
my sleep?"* still means scrolling through screens and comparing numbers by hand. The app never
connects one metric to another, or the present to the user's own past.

The app answers those questions from the user's own data, and every number it shows can be traced
to a computed statistic.

## Screens

| Screen | What the user does |
|---|---|
| **Welcome, sign up, sign in** | Learns what Patterns does, creates an account, and waits for the owner's approval (the app is in testing). |
| **Today** | Sees today's recovery score with its breakdown, last night's sleep, activity compared with their usual, and the morning check-in. |
| **Findings** | Reads what changed recently and why, each finding with its evidence. Answers the agent's context questions. |
| **Ask** | Asks questions about their data; answers come from the expert that owns the topic and cite evidence. |
| **Reminders** | Approves, mutes or declines reminders the agent proposes. Nothing is sent without approval. |
| **Data** | Connects their Google Health account (whole history, then kept synced), sees data coverage, picks light or dark, signs out; the owner also approves sign-ups. Takeout upload and deleting data are planned. |

## Agent-assisted logging (core planned capability)

The agent helps the person record workouts and food through conversation, alongside analysing
patterns. Activity owns workout proposals; Nutrition owns food proposals. The first local
implementation supports supplied-value food/workout drafts through Auto, review/edit/confirm
cards, cancellation and undo, plus saved entries on Data. Real Google writes are off by
default; one real food entry was created and undone on 2026-10-25. Food lookup, telemetry summaries and photos remain planned.

The shared flow is **collect missing details → propose → review/edit → confirm → execute → undo**.
The agent cannot grant approval or write to Google directly. Each confirmation applies to one
specific version of a proposal; edits require confirmation again. Cancellation writes nothing.

- **Workout:** collect activity, local start time/timezone and duration/end; ask for distance when
  relevant. A deterministic tool summarises available intraday heart rate and steps over that
  window, with coverage and evidence. Missing sensor data stays missing. Do not infer distance
  from an activity name or treat a workout log as extra steps/calories to add to device totals.
- **Food with supplied values:** collect meal/time, serving and provided energy/macros; retain
  their provenance as user-entered values, not independently verified measurements.
- **Food from photos or weights:** a later phase proposes food/portion and nutrient estimates,
  clearly labelled and editable before confirmation. A weight alone does not establish nutrient
  content. Model estimates are never represented as computed statistical Evidence or precise
  measurements; deterministic arithmetic may scale a known food's values to a serving.
- **Undo:** a person can request deletion of an entry this app created; show whether Google has
  confirmed the deletion. Never silently delete or overwrite another app's entries.

Validation catches malformed units, dates and unsupported fields. Unusual but possible entries
ask for clarification rather than imposing arbitrary medical or dietary limits. Logging gives no
medical, diet or energy-balance advice. Google write access is optional and requested explicitly;
existing read-only analysis must still work without it.

Confirmed records feed subsequent analyses through the normal source-aware sync. Store Google
record IDs and reconcile write-back echoes so each record is counted once, including existing
Cronometer/Apple Health duplication. Retain whether values were sensor-derived, user-entered,
food-database-derived or model-estimated.

Build locally first. Photos remain part of the intended demo after supplied-value logging;
hydration is a later extension. Jev classifies topic and request intent, the experts prepare
drafts, and server code alone enforces approval and execution. See the task-based
[tool plan and provider findings](agent-actions.md) and
[roadmap.md](roadmap.md#agent-assisted-logging-workstream-planned).

## Morning check-in

One question each morning: **"How do you feel today?"** on a 1 to 5 scale, with optional tags
(hard training, alcohol, late meal, stress, travel, feeling sick). It takes one tap and can be
skipped or changed the same day.

- **Ground truth for the recovery score:** it is the only way to show that our score tracks how
  the user feels better than Fitbit's readiness does (see Evaluation).
- **Context for the agent:** tags explain changes the sensors cannot see (*"recovery dropped on the
  3 days after tagged hard training"*).
- **Fixed tags instead of free text:** tags carry the context without giving the model a free-text
  input to inject instructions into.

## Which data is trusted

Fitbit's metrics are used as measured, with two exceptions:

- **Calories burned** is treated as low-confidence. Experts may describe relative changes (*"about
  15% above your usual"*) but never claims built on the absolute value, such as a calorie deficit
  or surplus. The verifier rejects energy-balance claims.
- **Readiness** is not used as the recovery signal. We compute our own recovery score and show
  Fitbit's readiness next to it for comparison.

Fitbit's sleep score and readiness exist only in Takeout exports: the live Google Health API has
neither, so nothing in the app depends on them. Readiness stays useful as the comparison in the
recovery evaluation.

## Recovery score

A deterministic score from 0 to 100, modeled on the inputs Bevel uses for its recovery score.
50 means a typical day for this person.

1. **Personal baseline.** For each input, today's value is compared with the person's own recent
   history: a robust z-score against the median and spread of the previous 28 to 60 days.
2. **Direction.** Each input is signed so that positive means better than usual:

   | Input | Better when |
   |---|---|
   | HRV (RMSSD during sleep) | higher |
   | Resting heart rate | lower |
   | Respiratory rate | lower |
   | Skin temperature variation | closer to baseline, in either direction |
   | Sleep: minutes asleep and efficiency | higher |

3. **Combination.** A weighted sum, with HRV and resting heart rate weighted most, mapped to 0 to
   100. Weights are fixed in code and versioned (`recovery_v1`, ...). They are not fitted to the
   user's check-ins, because a few weeks of ratings are too few to fit weights without fitting
   noise.
4. **Breakdown.** Every score lists each input's deviation and its contribution in points, so the
   app and the agent can explain it.
5. **Missing data.** No HRV or resting heart rate from last night means no score that day, not an
   estimate. Too little history for a baseline also means no score.

## Experts

Questions are handled by a specialist that owns a set of metrics. **Only the owner makes claims
about a metric**; any expert may read other experts' metrics to explain something.

| Expert | Owns | Reads |
|---|---|---|
| **Sleep** | sleep duration, time in bed, efficiency, sleep stages, bedtime | activity, check-in tags |
| **Recovery** | recovery score and breakdown, HRV, resting heart rate, respiratory rate, skin temperature, Fitbit readiness (Takeout only, for comparison) | sleep, training load, check-ins |
| **Activity** | steps, distance, active zone minutes, activity minutes, calories burned (low-confidence); cardio load from Takeout only | recovery, sleep |
| **Nutrition** (*to build*) | intake logged in Cronometer and synced through Google Health: energy, macros and 34 nutrients | sleep, activity |

Wear time and data coverage are shared: every expert must account for low-wear days.

## Routing

A fast classifier (Jev, a typed decision model) answers two things about each question, in one
call. Its **topic**: a probability for each of sleep, recovery, activity, nutrition, general and
out of scope. And, separately for each expert, whether answering **needs** that expert's data
(yes/no, as a probability). A single topic distribution cannot mark a question as cross-domain: its
spare probability is uncertainty, not a second topic. Code decides what to do with the answers:

- **Clear topic:** that expert leads.
- **Needs other experts' data** (a cross-domain question such as *"did my late nights hurt my
  recovery?"*): the lead consults those experts as tools; one answer, one owner, verified once.
  **Consulting is the router's decision**, not the depth's and not the lead's.
- **Low confidence:** the general agent answers.
- **Out of scope** (medical questions, requests unrelated to the user's data): refused without
  calling the LLM.

Only the question text is sent to the classifier, never the user's data. If it fails or times out,
a keyword rule over metric names routes the question instead.

## Asking a question

The Ask screen opens as an empty page with a compact input; the conversation takes over once the
first message is sent. The input has three controls:

- **Expert:** *Auto* by default, which routes as above. A user who already knows the topic can pick
  an expert, and the question goes straight to it. The scope check still runs on every message,
  so picking an expert cannot get around the refusal of medical questions, and the router still
  decides which other experts it consults. Nutrition is listed but disabled until nutrition data
  exists.
- **Depth:** *Quick* (the default) gives the expert a small tool budget; *Deep* lets it test more
  windows. Consults the router allows add their own budget at either depth. This is the latency
  and cost trade-off made visible, and both settings are measured in the evaluation.
- **Attach:** a recent finding or a metric, shown above the input, which decides the topic: its
  owner leads unless the user picked an expert, and an attached finding's evidence can be cited.

Every answer says which expert gave it, whether the router or the user chose that expert, and
which experts it consulted.

## What the agent may do, and what it asks first

- **Explain:** findings and answers, every number from a tool, every claim verified.
- **Ask, when it is worth it:** only about a change that is large, lasting and still unexplained
  after the agent tested its hypotheses. Questions are short and multiple choice, always with
  "rather not say" and a skip; never about feelings or personal difficulties. A dismissed
  question is not asked again, and the agent backs off after dismissals.
- **Remember, leanly:** context answers, past findings, check-ins and preferences, stored as short
  structured facts; only facts relevant to the current question are loaded, and facts that never
  matter fade out. New facts the agent wants to keep are confirmed by the user first.
- **Propose reminders** and **N-of-1 experiments** (for example "bedtime before midnight for 10
  days"): the agent tracks an accepted experiment and reports whether the metric changed,
  comparing the experiment window with the user's baseline.

Any user must approve before a reminder is scheduled, an experiment starts, a new fact is saved
to memory, or data is deleted.

All four experts (sleep, recovery, activity, nutrition) are part of the demo.

## Rules for every answer

- Numbers come from deterministic tools; the model only chooses what to compute and writes text
  that cites evidence.
- No medical diagnosis or advice. The app describes patterns in the user's own data.
- A claim the verifier cannot match to evidence is repaired once, then dropped.

## Evaluation tied to these decisions

- **Recovery score:** rank correlation of our score and of Fitbit readiness with the morning
  check-in over the same days, and the days where the two disagree most. With one or two people
  and a few weeks of data this is a pilot comparison, and is reported as such.
- **Routing:** accuracy, latency and cost of Jev against an LLM router and the keyword rule, on a
  labeled set of questions.
- **Experts:** the same evaluation suite run on the expert system and on a single general agent,
  to show whether the split is worth it.

## Open

- **Nutrition:** which daily nutrient columns to keep, and how to avoid counting Cronometer's daily
  total and its per-entry Apple Health copies twice (both arrive through the API). Takeout exports
  carry no nutrient values at all.
- **When the agent runs:** after each upload, on a schedule, or on demand.
- **History:** whether past reports and findings are browsable, or only the latest.

## Recorded routes and regions (optional, planned)

An extra after the logging flow: show where GPS-recorded walks/runs happened, or coarse map
regions, using Google Health exercise routes. This is not a reconstruction of every daily step.
A daily count alone carries no location. Fitbit Air uses the phone's connected GPS during
recorded exercise; without recorded coordinates the app must show location as unavailable.

Google exposes route coordinates through `exportExerciseTcx` (TCX), with separate
`googlehealth.location.readonly` consent in addition to activity access. The existing app does
not request this permission or sync routes. Start with recorded workout routes; only show step
counts for a route/region when the recorded session or a valid time-aligned step stream supports
that attribution. Keep the unlocated remainder explicit, and never distribute a daily total
across map regions by guessing.

Keep this optional and separate from the core agent milestone. Prefer coarse regions initially;
precise coordinates stay out of prompts and traces. Do not add continuous phone tracking or a
geocoding provider as part of this proposal. Validate GPS availability, gaps, denied permission,
time alignment and per-user access before implementing map UI.

Sources checked 2026-10-24: [Google workout routes](https://developers.google.com/health/data-types/workouts),
[TCX export](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/exportExerciseTcx),
[Fitbit Air connected GPS](https://support.google.com/googlehealth/answer/14225688?hl=en).
