# Roadmap

The approved plan from here to the demo (around the end of November 2026), agreed on 2026-10-21
after a 20-question planning session. Current state: [status.md](status.md). Each item ships as
its own pull request ([AGENTS.md](../AGENTS.md)).

**Most of the build happens in the next two weeks**; the rest of November is buffer and
hardening, so a big obstacle (API limits, deployment, model behaviour) still leaves time to
recover. The agent and its evaluation come first: they carry most of the grade.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | User | Students who train and wear a Fitbit |
| 2 | Demo wow | **The agent investigates a change live**: notices it, tests hypotheses with tools, explains the cause with evidence, while the trace shows each step |
| 3 | Home | Today dashboard (recovery ring, sleep, activity vs usual, check-in) + the agent's findings |
| 4 | Proactivity | Daily run after the morning sync, notification when something is worth seeing |
| 5 | Router | Jev in the app; evaluation compares Jev vs LLM router vs keyword rule (accuracy, latency, cost) |
| 6 | Experts | Separate expert agents (own prompt, own tools, own guardrails), **compared against one general agent as the baseline** |
| 7 | Reasoning | Hypothesis-test loop: screen → hypotheses → test with tools → update → claims → verifier |
| 8 | Loop code | Our own loop on the OpenAI API (no framework) |
| 9 | Memory | Context answers, past findings, check-ins/tags, preferences; **lean**: short structured facts, retrieve only what is relevant, drop what never matters |
| 10 | Approval (all users) | Reminders, experiments, saving new facts to memory, deleting data |
| 11 | Actions | Reminders + N-of-1 experiments the agent proposes, tracks and evaluates |
| 12 | Models | Small model for tool loops and routine runs; large model only for final write-ups and hard cross-domain questions |
| 13 | Budget | $20 cap until the final week, then bigger evaluation and user-testing runs; hard spending cap in code |
| 14 | Headline result | Accuracy of found changes and their causes on synthetic people with planted changes, vs baselines, plus unsupported-claim rate and cost |
| 15 | Testers | 3–5 friends as Google test users: interviews, real-data audit, demo credibility |
| 16 | Platforms | Android (EAS) + web first; Apple decision mid-November |
| 17 | Jad | To be decided |
| 18 | Done means | Deployed agent + evidence: online, investigates live data with traces, beats baselines, handles attacks live; polish second |
| 19 | Asking users | Ask when needed, **only if worth it**: large, lasting, still-unexplained changes; gentle, optional ("rather not say", skip); never about feelings or hardship; back off after dismissals, never re-ask the same thing |
| 20 | Experts at demo | All four: Sleep, Recovery, Activity, Nutrition |

## Agent design

**LLM layer** (`backend/app/agent/llm.py`): OpenAI chat with tool calling and structured outputs,
timeouts, retries, token and cost accounting per call, a per-run budget (tool calls, tokens,
dollars) and a global spending cap; `ScriptedLLM` fake replays canned turns so CI never needs a
key. Model per role: `small` for loops, `large` for write-ups.

**Tools** (`backend/app/agent/tools.py`): validated, JSON-schema wrappers over the existing
deterministic tools in `backend/app/analysis/tools.py` (`describe`, `coverage`,
`compare_windows`, `trend`, `correlate`) plus new ones: `change_points`, `weekday_split`,
`lagged_correlate`, `checkins` (ratings and tags), `memory_lookup`. Every result is an `Evidence`
(`backend/app/analysis/evidence.py`). Tools only accept metric names and windows; data access is
server-side and per user. Each expert sees only the tools and metrics it owns (+ read-only
access to others' via consult).

**Experts** (`backend/app/agent/experts.py`, built): Sleep, Recovery, Activity, Nutrition, each =
system prompt + owned metrics (from `docs/product.md`) + the metrics it reads + guardrails (no
medical advice; calories-burned low-confidence; no energy-balance claims); only the owner makes
claims about a metric. `consult(expert, question)` is a tool that runs another expert with a
smaller budget and returns its verified claims and their evidence; the router decides who may be
consulted.

**General agent** (baseline): same loop, all tools, no routing, no consults.

**Router** (`backend/app/agent/router.py`, built): one Jev call with a choice over {sleep,
recovery, activity, nutrition, general, out_of_scope} and a yes/no per expert (does the question
need its data) → code thresholds decide lead + consults / general / refuse. On failure the keyword
rule routes; the LLM router is kept for the evaluation's comparison. Only the question text leaves
the server.

**Investigation loop** (hypothesis-test): state = {change, hypotheses[], evidence[], budget}.
1. Screen owned metrics (reuse `backend/app/analysis/screen.py`).
2. LLM proposes hypotheses from a fixed menu + free form (bedtime shift, training load, low wear,
   tagged event, nutrition change, illness tag, data artifact).
3. For each, the LLM picks a tool call; code runs it; evidence attached; hypothesis marked
   supported / refuted / untestable.
4. Stop when resolved or budget spent; LLM drafts claims citing evidence ids.
5. **Verifier** (deterministic, `backend/app/agent/verifier.py`): ids exist, numbers and directions
   match the evidence, `sufficient` evidence only, no medical or energy-balance claims; failing
   claims repaired once, then dropped.
6. If the top change stays unexplained and passes the "worth asking" gate (#19) → one gentle
   multiple-choice question.

**Memory** (DB tables by migration): `memory_facts` (kind, text, structured value, source,
created, last_used, uses), `findings` history, `checkins`. Retrieval by metric/expert/time
relevance, top-k small; facts unused for N runs decay out. New facts proposed by the agent need
user approval (#10).

**Actions:** reminders (existing contract in `mobile/src/api/types.ts`) and N-of-1 experiments:
proposal (behavior, metric, duration ≥ 10 days) → user accepts → baseline vs experiment window
evaluated with `compare_windows` at the end → result reported with evidence.

**Daily run:** after the morning sync, each expert screens its metrics, investigations run
within budget, the report is stored, a notification is sent if a finding passes the bar.

**Tracing:** every run, LLM call and tool call → Langfuse (latency, tokens, cost, retries,
verifier rejections); API metrics → Prometheus/Grafana; cost per successful task.

## Schedule: most of the build in two weeks, the rest is buffer

Front-loaded on purpose: if a big obstacle hits (API limits, deployment, model behaviour), there
are still three weeks to recover. Each item is its own PR per AGENTS.md; risky items go first.

**Sprint 1 (Oct 22–28): the agent works end to end**
1. Days 1–2: LLM layer + `ScriptedLLM`, cost accounting and budgets; agent tools wrapping the
   analysis (+ change points, weekday split, lagged correlation, check-ins, memory lookup).
2. Days 2–3: general agent with the hypothesis loop; verifier; local JSON traces. **Milestone:**
   explains a planted change on a synthetic person, and a real change on live data.
3. Days 3–4: four experts, consult tool, router (Jev + keyword + LLM fallbacks). **Done**
   (PRs #28, #29); results and open issues in [experiments.md](experiments.md) and
   [status.md](status.md#open-issues).
4. Days 4–5: memory, findings and check-in tables; "worth asking" questions. **Done** (PRs #36,
   #37).
5. Days 5–7: API serves live data from the DB; `/reports`, `/chat`, `/checkins`, `/sync`
   endpoints; the app's Today, findings, Ask and Data screens move off mock data. **Done** except
   `/checkins` (PRs #44, #45, #47, #48): each person's own data, real chat, Google sync from the
   app. Also done early: the landing page, palette and sign-in pages (#39, #40, #46).

**Sprint 2 (Oct 29–Nov 4): complete and online**
1. Recovery score + morning check-in; nutrition columns (deduplicated) + nutrition expert.
2. Daily run after sync + notifications; reminders and N-of-1 experiments with approval.
3. Langfuse tracing + cost per task; Prometheus/Grafana for the API.
4. Accounts (email/password) and per-user Google sign-in with encrypted tokens. **Done early**
   (PRs #41–#43, #47, #48): our own sign-up, each approved by the owner; signing in with Google
   was dropped (it needed a second, public Google app).
5. Deployment: Railway (API + Postgres), Vercel (web), EAS Android; deploy from `main` after CI.
   **Next**, moved first: phones need a public HTTPS backend to connect Google.
6. Evaluation v1: synthetic people with planted changes and causes (extend
   `backend/app/synthetic.py`), dev/held-out split, all baselines (stats-only, LLM without
   tools, general agent, experts, experts without verifier), router comparison, deterministic
   eval gate in CI.

**Buffer and hardening (Nov 5–30)**
- Friends onboarded as test users; real-data audit; interviews for the problem statement.
- Attack suite (prompt injection, medical questions, cross-user access, malicious uploads,
  model failures), each failure turned into a regression test; failure matrix; threat model.
- Larger paid evaluation runs in the last week; results, report, poster, demo script with live
  edge cases; `v1.0-demo` tag. UI polish only after all of the above.

**Risks to watch first:** Jev availability and pricing (fallbacks ready from day 3); Google
Testing-mode 7-day sign-ins on the deployed app (reconnect flow); OpenAI cost (hard cap);
Railway + Postgres setup (deploy a skeleton early in Sprint 2, not at its end).

## Inputs needed

- An OpenAI API key in `.env` (as `FA_OPENAI_API_KEY`) before the first real agent runs, around
  Oct 24; CI uses the scripted fake and needs no key.
- A TypeSafe (Jev) API key for the router, around Oct 25.
- Friends' Google accounts added as test users before deployment, around Nov 1.
- Jad's role.

## Verification

Per PR: `ruff`, `pytest`, mobile checks per `AGENTS.md`; agent PRs also run the scripted-LLM
scenarios in CI and one real run on live data (cost and trace reported, no personal values
printed). Milestone checks: in Sprint 1, the general agent explains a planted change on a
synthetic person end to end and the router sends a labeled question set correctly; in Sprint 2,
the evaluation report compares all baselines on the held-out set and the deployed app works on a
phone.
