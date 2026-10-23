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
| **Today** | Sees today's recovery score with its breakdown, last night's sleep, activity compared with their usual, and the morning check-in. |
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
- **Attach:** a recent finding or a metric, shown above the input, which decides the topic.

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
