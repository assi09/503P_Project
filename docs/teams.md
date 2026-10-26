# Teams: a weekly report for a supervisor

A supervisor (a manager, a department head) invites a group of employees into a **team**. Every
week the system writes the supervisor a report on how the team's sleep, activity and recovery
changed, from the members' own data. The supervisor has their own view in the app; they need no
Fitbit, and if they have one they connect it like anyone else.

This sends health data toward an employer, so the design starts from what the supervisor may
**not** see. Status: planned, nothing built yet.

## What the supervisor sees, and what they never see

| Sees | Never sees |
|---|---|
| The team's name, invite code and number of active members | Who the members are, or who joined or left |
| Weekly aggregates across members: median change per metric, how many moved up and down, a weekday pattern, the evidence behind each | Any one person's values, days, workouts, chats, check-ins or findings |
| Which metrics had too little data to report | A figure built from fewer than 5 people |

- **Minimum group of 5.** A figure is shown only if at least 5 members contributed to it; a metric
  with fewer is listed as "not enough data". With fewer than 5 active members no report is made.
- **Aggregates only, everywhere.** Member ids and per-person values never enter evidence records,
  the model's prompt, the stored report or the email. Evidence holds counts, medians, quartiles
  and p values.
- **No medical or employment judgments.** The report describes patterns in the team's data; it
  does not diagnose, rank people, or suggest decisions about anyone. Wording stays neutral
  ("time asleep fell", not "the team is exhausted").

## Joining and leaving

1. The owner of the app marks an account as a supervisor (`python -m app.auth make-supervisor`).
2. The supervisor creates a team and gets an invite code, which they can rotate at any time.
3. An employee enters the code in Settings and reads a consent screen: what is shared (weekly
   team aggregates with at least 5 people, no names, no daily values), with whom, and how to
   leave. Nothing is shared until they confirm.
4. Settings lists every team the person shares with, with a Leave button. Leaving takes effect
   from the next report; reports already made keep their aggregates, which identify no one.

Joining, leaving and code rotation are written to the audit log. The consent text is versioned,
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
3. Team statistics with calibration tests.
4. The weekly report: templated, then the language-model text with the verifier and fallback,
   then the CLI. One real run on a synthetic team, logged in [costs.md](costs.md) and
   [experiments.md](experiments.md).
5. Email: a console mailer for development and an HTTP provider.
6. App, employee side: join, consent, leave.
7. App, supervisor side: Team tab, report, team settings.
8. Scheduling, with the deployment.

## Open

- Which email provider, once the backend is deployed.
- Whether 5 is the right floor for a demo team; it can only go up, never down.
- Whether a supervisor can run more than one team (the model allows it; the first UI shows one).
