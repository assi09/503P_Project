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
| **Today** | Sees today's recovery score with its breakdown, Fitbit's sleep score, activity compared with their usual, and the morning check-in. |
| **Findings** | Reads what changed recently and why, each finding with its evidence. Answers the agent's context questions. |
| **Ask** | Asks questions about their data; answers come from the expert that owns the topic and cite evidence. |
| **Reminders** | Approves, mutes or declines reminders the agent proposes. Nothing is sent without approval. |
| **Data** | Uploads a Google Takeout export, sees data coverage, deletes their data. |

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

Fitbit's sleep score is used as-is.

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
   | Sleep score | higher |

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
| **Sleep** | sleep duration, time in bed, efficiency, Fitbit sleep score, sleep stages, bedtime | activity, check-in tags |
| **Recovery** | recovery score and breakdown, HRV, resting heart rate, respiratory rate, skin temperature, Fitbit readiness and its sub-scores | sleep score, training load, check-ins |
| **Activity** | steps, distance, active zone minutes, cardio load and acute:chronic ratio, activity minutes, calories burned (low-confidence) | recovery, sleep |
| **Nutrition** (*open*) | intake from Cronometer via Google Health | sleep, activity |

Wear time and data coverage are shared: every expert must account for low-wear days.

## Routing

A fast classifier (Jev, a typed decision model) labels each question with one of: sleep,
recovery, activity, nutrition, general, out of scope. It returns a probability per label, and code
decides what to do with them:

- **One clear label:** that expert answers.
- **Several likely labels** (a cross-domain question such as *"did my late nights hurt my
  recovery?"*): the most likely expert leads and consults the others as tools; one answer, one
  owner, verified once.
- **Low confidence:** the general agent answers, or the app asks the user to clarify.
- **Out of scope** (medical questions, requests unrelated to the user's data): refused without
  calling the LLM.

Only the question text is sent to the classifier, never the user's data. If it fails or times out,
a keyword rule over metric names routes the question instead.

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

- **Nutrition:** the format and completeness of Cronometer data in a Google Health export.
- **When the agent runs:** after each upload, on a schedule, or on demand.
- **History:** whether past reports and findings are browsable, or only the latest.
