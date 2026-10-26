# Teams: a weekly report for a supervisor

A supervisor (a manager, a department head) invites a group of employees into a **team**. Every
week the system writes the supervisor a report on how the team's sleep, activity and recovery
changed, from the members' own data. The supervisor has their own view in the app; they need no
Fitbit, and if they have one they connect it like anyone else.

This sends health data toward an employer, so the design starts from what the supervisor may
**not** see. There are two layers. Joining a team shares only team aggregates. Showing your own
named levels is a separate switch that each person turns on and off themselves. Status: planned,
nothing built yet.

## What the supervisor sees, and what they never see

| Sees | Never sees |
|---|---|
| The team's name, invite code and number of active members | Who joined or left, or who has not opted in |
| Weekly aggregates across members: median change per metric, how many moved up and down, a weekday pattern, the evidence behind each | A team figure built from fewer than 5 people |
| Which metrics had too little data to report | Anyone's daily values, other metrics, workouts, chats, check-ins or findings |
| **Only for people who opted in:** their name and this week's recovery, sleep, strain and stress, each as a level against their own baseline plus the week's average | Any named data about someone who has not opted in, or after they switch it off |

- **Minimum group of 5.** A figure is shown only if at least 5 members contributed to it; a metric
  with fewer is listed as "not enough data". With fewer than 5 active members no report is made.
- **Aggregates only, everywhere else.** Member ids and per-person values never enter team
  evidence records, the model's prompt, the report text or the email. Evidence holds counts,
  medians, quartiles and p values. Named levels appear only in the supervisor's view in the app,
  as a table, and the agent never writes about named people.
- **No medical or employment judgments.** The report describes patterns in the team's data; it
  does not diagnose, rank people, or suggest decisions about anyone. Wording stays neutral
  ("time asleep fell", not "the team is exhausted").

## Joining and leaving

1. The owner of the app marks an account as a supervisor (`python -m app.auth make-supervisor`).
2. The supervisor creates a team and gets an invite code, which they can rotate at any time.
3. An employee enters the code in Settings and reads a consent screen: what is shared (weekly
   team aggregates with at least 5 people, no names, no daily values), with whom, and how to
   leave. Nothing is shared until they confirm.
4. **Named levels are a second, separate switch** ("Show my weekly levels to <supervisor>"),
   off by default, with its own consent screen. The screen shows exactly the row the supervisor
   would see. Not opting in changes nothing else: the person still counts in team aggregates.
5. Settings lists every team the person shares with, the switch, and a Leave button. Leaving
   takes effect from the next report; reports already made keep their aggregates, which identify
   no one, but named levels of someone who left or switched off are no longer shown, even for
   past weeks.

Joining, leaving, switching named levels on or off, code rotation and every time a supervisor
opens named levels are written to the audit log. The consent text is versioned,
and each membership records the version the person agreed to.

## How the numbers are made

All deterministic, in `backend/app/analysis/team.py`; the language model computes nothing.

1. **Each member on their own history.** A member's days come from one source, as everywhere
   else, with low-wear days removed. For each metric: the mean of the last 7 days minus the mean
   of the 28 days before.
2. **Only changes are pooled.** People differ in device, baseline and habits, so raw values from
   different people are never averaged; each person's *change* against their own baseline is.
3. **Team change per metric.** A Wilcoxon signed-rank test of whether the members' changes are
   centred on zero, with the median change and the counts up and down. Benjamini-Hochberg across
   metrics, as in the personal screen.
4. **Weekday pattern.** Each member's deviation from their own weekly mean, by weekday, pooled.
5. **Privacy floor** applied last: anything with fewer than 5 contributors is dropped.

Tests check these properties over many seeds: false-positive rate near alpha when nothing
changed, power on planted team-wide effects in synthetic members, and suppression below 5.

## Named weekly levels (opt-in)

For each person who opted in, the Team tab shows one row for the past week:

| Score | Weekly value | Level |
|---|---|---|
| Recovery | mean of the daily [recovery score](product.md#recovery-score) | below / usual / above |
| Sleep | mean time asleep | below / usual / above |
| Strain | mean daily [strain](scores.md) | below / usual / above |
| Stress | mean daily [stress](scores.md) | below / usual / above |

- **Each level is measured against the person's own previous four weeks.** "Usual" is the middle
  half of their weekly means (the same idea as Today's usual range), so a level says "unusual for
  them" and never compares people. Rows are listed alphabetically, never ranked.
- A score with fewer than 4 days of data that week shows "not enough data" instead of a level.
- Weekly values only, no days, and only these four scores.
- The person sees their own row in Settings, exactly as the supervisor sees it.

## The weekly report

- **Text.** One language-model call per team per week receives only the aggregate evidence and
  writes the narrative, citing evidence ids. The claim verifier checks every number against the
  evidence it cites. On a model error, an exceeded budget or rejected claims, a templated text
  (the same style as the personal report) is used instead.
- **Cost.** A cap of about $0.02 per team per week (`FA_TEAM_REPORT_CAP_USD`); each report stores
  its cost.
- **When.** `python -m app.teams weekly` makes every team's report for the past week; the deployed
  platform's scheduler runs it on Mondays. A team and week are made once, so reruns are safe. The
  supervisor can also ask for one on demand, rate-limited.
- **Delivery.** In the app, a Team tab for supervisors with this week's report and past weeks.
  By email, the headline, the aggregate figures and a link to the app; the email provider's key
  lives only in `.env`. Real emails are sent only after deployment.

## Build order

Small PRs, each green and verified:

1. This document.
2. Roles, teams and memberships (migration 0009), join and leave, the team API, access-control
   tests.
3. Strain and stress scores ([scores.md](scores.md)): the daily inputs from minute heart rate
   at sync, the scores, their tests, then on Today.
4. Team statistics with calibration tests, and the named weekly levels behind the opt-in.
5. The weekly report: templated, then the language-model text with the verifier and fallback,
   then the CLI. One real run on a synthetic team, logged in [costs.md](costs.md) and
   [experiments.md](experiments.md).
6. Email: a console mailer for development and an HTTP provider.
7. App, employee side: join, consent, leave, the named-levels switch.
8. App, supervisor side: Team tab, report, named levels, team settings.
9. Scheduling, with the deployment.

## Open

- Which email provider, once the backend is deployed.
- Whether 5 is the right floor for a demo team; it can only go up, never down.
- Whether a supervisor can run more than one team (the model allows it; the first UI shows one).
