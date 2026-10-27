# The last four weeks

The working plan from 2026-10-27 to the end of the project. **Everything planned is built and
evidenced by Sunday 2026-11-23**; the two weeks after (Nov 24 – Dec 7) are kept free for surprises,
rehearsal and only small fixes. The poster pitch is done; this plan covers the final submission:
live demo and presentation (with a final poster if the instructor asks for one), the repository with
setup and reproducibility, the evaluation and its results, traces and operational metrics, failure
and threat analysis, architecture and API documentation, and the final technical report. Every
applicable bonus practice is in it.

Each item is its own small PR, per [AGENTS.md](../AGENTS.md). Open issues are the numbered list in
[status.md](status.md#open-issues); they are referred to here as "issue n".

## The goal: one agentic system, not a set of screens

Today the parts work one by one: Today shows numbers, Ask answers, logging drafts entries, teams
send a weekly email, Reminders is a mock. The last four weeks join them into **one loop the agent
runs with the person**:

```
        sync (every morning)
              │
     ┌────────▼─────────┐   notices: changes, missed check-ins, expired Google sign-in,
     │    daily run     │   experiment days, reminders due, its own earlier proposals
     └────────┬─────────┘
              │ investigates the one change worth it (verified claims, evidence)
              ▼
   Today note ─── proposes ──► reminder · experiment · fact to remember   (person approves)
              │                       │
              │                 acts: reminds, records adherence, logs drafts the person confirms
              ▼                       │
   follows up: "did the wind-down reminder change your bedtime?" · experiment results
              │
              ▼
   memory (findings, results, check-ins, facts) ──► every later answer, the weekly recap,
                                                     and (aggregated, k ≥ 5) the team report
```

What makes it one system:

- **One daily run** drives Today's note, reminders, experiment days and follow-ups; the weekly
  run adds a personal recap next to the team report.
- **One proposals inbox**: everything the agent wants to do (remember a fact, set a reminder,
  start an experiment, log a draft) arrives as the same kind of card, approved or declined the same
  way, with one audit trail. Nothing happens without approval (decision 10).
- **One memory**: findings, experiment results, reminder effects, check-ins and approved facts,
  used by every answer and shown in one "What Patterns knows about you" page the person can edit.
- **One voice** (`app/agent/voice.py`) and **one rule**: every number links to its evidence.
- **One way in**: onboarding that connects Google, sets the person's goal, offers a first
  experiment and explains what the agent will and will not do.

## Workstreams

### A. The chat and the agent: fix what is weak, give it more tools

Fixes, from what the deployed app and the open issues show:

1. **The summary fallback**: when the summary fails its check twice, the joined claims read like a
   report. Write a deterministic summary instead (steady metrics in one sentence, changes first),
   and allow one more repair round for summary-only problems.
2. **Verdicts that depend on how many tests ran** (issue 20) and **"no clear change" hiding a real
   one** (issue 14): a fixed family of tests per question type, and borderline results said as
   borderline.
3. **Consults not followed** (issue 23) and **tests the question did not need**; **quick depth
   running out** (issue 13): plan the tests first, then spend the budget.
4. **Recomputing instead of citing memory** (issue 9); **answers missing a part of the question**
   (issue 4); **overstating in generic words** (issue 11).
5. **The reaction dropping "or look at your data"**, and **facts never proposed** (issue 15) with
   the screen to approve them (issue 19).
6. The **advice guard** on a held-out set (issue 10); cosmetic quote marks (issue 7).

New tools, so the agent can do what the system needs:

| Tool | What it gives the agent |
|---|---|
| `design_experiment`, `experiment_status`, `analyse_experiment` | the experiment workstream (B) |
| `propose_reminder`, `reminder_effect` | reminders it can suggest and later judge (C) |
| `workouts` | the workouts in a period, with type, duration and zones, from the stored sync |
| `checkins` | morning check-in ratings and tags, for "on days I felt tired…" |
| `habit_impact` | a journal tag against matched days without it, corrected for the number of tags |
| `memory_lookup` | the person's findings, results and facts by topic, so it cites instead of recomputing |
| `team_aggregate` (supervisors only) | the team's weekly aggregates, never below 5 people (D) |

Each tool validates its input, raises `ToolError`, returns `Evidence`, and gets tests including the
unhappy paths. Prompt and tool versions are recorded on every trace (workstream I).

### B. Personal experiments (the headline feature)

As designed in [product.md](product.md#personal-experiments-headline-agentic-feature-planned) and
[architecture.md](architecture.md#experiment-runner-planned), in the order of
[roadmap.md](roadmap.md#personal-experiments-workstream-planned). **The owner's real experiment must
start by Wednesday Nov 5** to have three weeks of data before Nov 23, so the statistics tools, state,
approval and daily recording come first and the report screen last.

### C. Reminders for real

Replace the mock ([ui-plan.md](ui-plan.md#reminders), step 5):

- Backend storage and API (kinds: wind-down before a bedtime, move after long sitting, planned
  workout, logging and check-in prompts, experiment assignments, "reconnect Google").
- The agent proposes reminders with their evidence; the person edits the schedule, quiet hours and
  daily cap, and approves.
- Delivery: phone notifications in the installed app (`expo-notifications`), web push for the home
  screen web app where the browser allows it, and the in-app list everywhere. Email only for
  "reconnect Google".
- Follow-up: `reminder_effect` compares the target metric before and after, with a test, and the
  result goes to memory ("since the wind-down reminder, bedtime moved 25 minutes earlier").

### D. Teams, improved

Built: memberships with consent, team statistics (never below 5), opt-in named weekly levels, the
weekly report with checked prose and figures, the supervisor's Team tab, the Monday email
([teams.md](teams.md)). Next:

- **Invite by link** (the code inside a link) and a first-run screen for people who join that way.
- **Participation** for the supervisor: how many members synced this week, as a count only.
- **Trends over weeks** in the report, not just last week against the one before.
- **Ask about the team** for supervisors: the agent answers questions about the team's report with
  `team_aggregate` only, under the same floor of 5 and the same verifier.
- **A team challenge** the supervisor proposes (for example, a sleep-before-midnight week), joined
  individually and reported only in aggregate.
- **A verified sending domain** for Resend, so the email reaches any supervisor.
- Tested in the pilot (F) with a real team of about 10.

### E. Joining it up (the united system)

- The **daily run** as a Railway cron after the morning sync, like `weekly-email`: screen,
  investigate the top change, advance experiments, queue reminders, write Today's note. No model
  call on quiet days. Today's note returns, switchable off in Settings (it was skipped earlier at
  the owner's request; now it carries experiments and reminders too).
- The **proposals inbox** and the **memory page** described above.
- **Onboarding** and a **weekly personal recap** (in the app and by email, opt-in).
- **Accounts for real users**: email verification and password reset now that email works
  (issue 16), "delete my account and data", the session cookie on the web instead of
  localStorage (issue 16), the OAuth code out of the access log (issue 21), `?google=` cleared
  from the address (issue 18).
- Smaller planned pieces only if time allows, in this order: the journal with habit impact
  (needed by `habit_impact`), the weekly workout summary, fitness age.

### F. A pilot with about 10 people

Friends who train and wear a Fitbit or Pixel Watch, one team, a supervisor (to be decided).

- **Before (week 1)**: their Google accounts added as test users (the OAuth app stays in Testing:
  at most 100, sign-ins expire after 7 days); a consent and privacy page; account deletion; caps
  raised for 10 people (`FA_CHAT_DAILY_CAP_TOTAL_USD` about 1.50); an invite message and a
  feedback form.
- **During (weeks 2–3)**: about three weeks, three Monday team reports; daily log checks; each
  problem a Failure Matrix row and a regression test.
- **After (week 3)**: a 5-minute survey and 3–5 interviews; usage, success, cost and latency per
  person from the traces; the recovery score against check-ins (issue 24). Reported only in
  aggregate; no tester's data enters git.

### G. Evaluation (deliverable, 20%)

A harness in `eval/` that anyone can rerun (`python -m eval.run --suite …`), writing results to
`eval/results/` with the code version, prompt versions, seed and cost:

| Suite | Measures | Against |
|---|---|---|
| Planted changes | finding a planted change and its cause on synthetic people; false reports on calm people | templated screen (no LLM), LLM without tools, general agent, experts, experts without verifier |
| Experiments | detection, false alarms near alpha, effect bias and interval coverage, "too few days" honesty | habit yes/no association (WHOOP-style), before/after windows |
| Router | accuracy, latency, cost on a labeled held-out question set (including chat and logging questions) | Jev, LLM router, keyword rule |
| Claims | unsupported-claim rate, overstatements, advice leaks | with and without verifier and guard |
| Red team | prompt injection, medical questions, cross-user access, unsafe experiments, unauthorized writes | expected refusals and blocks |
| Cost and latency | cost per successful task, end-to-end and per-step latency | per depth and per expert |

Scenarios are checked with the deterministic tools before they grade the agent (issue 6); the
consult policy A against B (issue 2) and the thresholds (issue 5) are settled by it. Paid runs are
budgeted in [costs.md](costs.md); **top up OpenAI to about $10–15 before week 3**.

### H. Reliability and security (deliverables, 15%)

- **Failure Matrix** (`docs/failure-matrix.md`): each component × failure (OpenAI, Jev, Google,
  database, email down or slow; malformed responses; rate limits; expired sign-ins; bad input),
  the behaviour, the test that proves it.
- **Threat model** (`docs/threat-model.md`): assets (health data, tokens, keys), actors, entry
  points (chat, uploads, OAuth, team codes), STRIDE-style threats, controls, residual risk.
- **Chaos tests** (fault injection on each external call), **load test** (k6 or Locust against a
  staging copy), **contract tests** (backend schemas against `mobile/src/api/types.ts`).
- The demo shows failures on purpose: Jev down, OpenAI over budget, an injection attempt, a
  medical question, another user's data requested, an unsafe experiment.

### I. AgentOps and observability (15%) and the bonus practices

| Bonus practice | Now | To do |
|---|---|---|
| Engineering workflow | PRs, protected `main`, ~100 merged PRs | GitHub Project with weekly sprints, an owner per issue, one required review |
| CI/CD and deployment | Actions; Railway and Vercel deploy after CI | a smoke test after each deploy, a release tag per week |
| Code quality | ruff | coverage (pytest-cov, jest) to Codecov, SonarCloud, coverage floor in CI |
| Agent evaluation in CI | none | a free gate on every PR (scripted model, deterministic suites, red-team set); a paid suite by hand with stored thresholds |
| Advanced AgentOps | cost per answer, a trace in memory | traces stored and sent to Langfuse (or OpenTelemetry), per call: latency, tokens, cost, tool failures, retries; a metrics page |
| DevSecOps | secret scanning and push protection | Dependabot, CodeQL, pip-audit and npm audit, Trivy on the image, Semgrep |
| Reproducible deployment | Dockerfile, automatic migrations, Railway config | a full-stack `docker compose up`, the cron config as code |
| Advanced testing | unit and scenario tests | contract, load, chaos and red-team suites (H) |
| Production monitoring | Railway's metrics | Sentry on the API and the web app, with alerts |
| Controlled evolution | feature flags such as Google writes | prompt and model versions on traces, comparisons between versions in the evaluation, flags for new features in the pilot |

### J. Documentation and the final deliverables

README quickstart (local and Docker), [deployment.md](deployment.md) kept current,
`docs/api.md` (endpoints, schemas, authentication, errors, from FastAPI's OpenAPI), the
architecture diagram updated, reproduction commands for every number in the report, the final
technical report, the presentation and demo script (with the failure cases in H), and a final
poster if the instructor asks for one (the pitch poster updated with results).

## Week by week

**Week 1 — Oct 27 to Nov 2: measure, secure, prepare**
- AgentOps: stored traces, Langfuse, prompt versions; Sentry. DevSecOps bundle, coverage,
  SonarCloud, GitHub Project and sprint issues.
- Evaluation harness and the free CI gate; the labeled router set started.
- Chat fixes A1 (summary fallback) and A5; experiment statistics tools with property tests (B).
- Pilot prerequisites: account deletion, consent page, email verification and reset, issue 21 and
  18; testers' emails collected and added as test users.
- **Done when**: every answer has a stored trace with cost and latency; CI runs the eval gate; the
  experiment statistics pass their property tests; testers can be invited.

**Week 2 — Nov 3 to 9: the agentic loop**
- Experiments: state, approval card, daily recording, screen. **Owner's experiment starts by
  Nov 5.**
- The daily run (cron), Today's note, the proposals inbox; reminders backend and agent proposals.
- New tools: `workouts`, `checkins`, `memory_lookup`; chat fixes A2–A4.
- **Pilot onboarding** (about 10 people, one team).
- **Done when**: a synthetic person goes through propose → approve → daily recording → result in
  tests; the pilot team exists; reminders are proposed and approved in the app.

**Week 3 — Nov 10 to 16: evidence**
- Reminders delivered as notifications, `reminder_effect`; team improvements (invite link,
  participation, trends, Ask about the team, challenge).
- Paid evaluation runs; red-team, chaos, load and contract suites; Failure Matrix and threat model.
- Pilot running; survey and interviews at the end of the week.
- **Done when**: the evaluation tables are filled with results; every red-team case is blocked or
  documented; the Failure Matrix covers every external dependency.

**Week 4 — Nov 17 to 23: finish and write**
- Experiment report screen and the owner's result; weekly personal recap; onboarding; memory page.
- Final report, API docs, README and reproducibility, demo script and presentation; poster update
  if needed.
- A dry run of the demo, including the failure cases; a `v1.0-demo` tag.
- **Done when**: someone outside the team can set up, run and reproduce the main results from the
  README; the demo works start to finish twice in a row.

**Buffer — Nov 24 to Dec 7**: surprises, rehearsal, only small fixes. No new features.

## Where every open issue goes

| Issue | Plan |
|---|---|
| 2 consult policy, 5 thresholds, 6 detectable scenarios, 20 verdict vs number of tests | evaluation (G), weeks 1–3 |
| 4 missing parts, 9 recomputing, 11 overstating, 13 quick depth, 14 hidden change, 23 consults | chat fixes A2–A4, week 2 |
| 7 quote marks, 15 facts never proposed, 19 facts screen | A5 and the memory page, weeks 1 and 4 |
| 10 guard misses implied diagnoses, 12 scope check when Jev is down | red team (H), week 3 |
| 16 no email check or reset, token in localStorage; 18 `?google=`; 21 code in the log | accounts (E), week 1 |
| 17 phones need the deployed backend | done: deployed on Railway and Vercel |
| 22 writes labelled "Cronometer" | investigate in week 3 if time allows; documented as a limitation otherwise |
| 24 recovery score not validated | pilot check-ins (F), week 3 |
| 25 workouts need a Google connection, 26 not seen in a real run, 27 old note wording | covered by the pilot; no work planned |

## Who does what

Karim with Claude Code: the code, the evaluation runs and the PRs. Jad: to be decided with Karim;
a natural split is the threat model, the Failure Matrix, the pilot (recruiting, survey,
interviews), the report and the presentation, plus reviewing PRs (needed for the review bonus).

## Risks

- **The experiment needs calendar time**: if it cannot start by Nov 5, the demo shows a synthetic
  experiment end to end and the owner's partial result.
- **Google Testing mode**: sign-ins expire weekly; the "reconnect Google" reminder and email cover
  it. Verification for production is out of reach.
- **Budget**: OpenAI about $5 left before a top-up; the pilot and the evaluation need about
  $10–15 more. Hard caps stay in code.
- **The healthcare exclusion** in the brief: Patterns is framed and built as performance and habit
  analytics for people who train; it never diagnoses or advises, and experiments exclude anything
  medical. Keep that framing in every deliverable.
- **Scope**: if a week slips, cut in this order: fitness age, weekly workout summary, team
  challenge, web push, the journal (keeping `habit_impact` on check-in tags).
