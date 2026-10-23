# Project status

The page to read first when picking the project up. Updated 2026-10-23.

## Objective

EECE 503N/798S course project (Path A, application), demo around the end of November 2026. An app
that analyzes a person's longitudinal Fitbit data and explains what changed and why, where **the
agent decides what to investigate and deterministic tools compute every number**. The instructor
requires a mobile app and a fully deployed system (backend online, installable app).

The grade weights idea and agentic justification (20%), agent performance and evaluation (20%),
AgentOps (15%) and reliability and security (15%), so **the agent and its evaluation are the
priority**; the UI and data plumbing exist to serve them.

## What works today

| Area | State |
|---|---|
| Data | Takeout import (legacy layout); **live Google Health API** sign-in, client and mapping to the daily table, verified against Takeout ([metrics.md](metrics.md#from-the-google-health-api)) |
| Storage | Postgres in Docker with the first migration (users, Google connections, daily metrics, sync runs); `python -m app.sync pull` stores live days |
| Analysis | deterministic tools returning `Evidence` (incl. change points with a permutation test, weekday split); 14-vs-28-day screen with FDR correction and a templated report (the no-LLM baseline) |
| Agent | LLM layer with cost accounting and budgets; validated toolbox; **general agent** (hypothesis-test loop, `submit_findings`, one repair round) and the **claim verifier**; first real run on a synthetic person explained the planted change correctly for $0.024; **experts** (sleep, recovery, activity; nutrition waiting for data) with ownership of claims and `consult`; **router** (Jev topic and per-expert needs, keyword fallback, LLM router for comparison) and the ask flow |
| API | `/health`, `/data/status`, `/reports/latest`, `/evidence/{id}`; single user, reads Takeout, no auth |
| App | Today, Ask (expert picker, quick/deep, attachments, routed answers on mock data), Reminders, Data; Expo SDK 57, runs in Expo Go and on the web |
| Engineering | protected `main`, PRs with both CI jobs required, ~160 backend and ~50 mobile tests |

**Not built yet:** the context builder and memory, the recovery score, nutrition
columns, the API serving live data, accounts, deployment, tracing and metrics, the evaluation
suite, the failure matrix and threat model.

## Local setup

1. Backend: `python3 -m venv .venv && source .venv/bin/activate && pip install -e "backend[dev]"`.
2. Database: `docker compose up -d db` (Postgres on port **5433**), then
   `alembic -c backend/alembic.ini upgrade head`.
3. `.env` at the repository root (git-ignored; copy `.env.example`): `FA_TIMEZONE`,
   `FA_EXPORT_DIR`, `FA_GOOGLE_CLIENT_ID` / `FA_GOOGLE_CLIENT_SECRET` for live data, and
   `FA_OPENAI_API_KEY`, `FA_TYPESAFE_API_KEY` and `FA_LLM_SPEND_CAP_USD` for the agent. Both API
   keys are set on Karim's machine; **budgets are about $5 each**, see [costs.md](costs.md).
4. Live data: `python -m app.sync connect`, then `check`, `compare --export Takeout`,
   `pull --email <account>`. Run from the repository root.
5. App: `cd mobile && npm ci && npx expo start` (Expo Go) or `npm run web`.

### The Google Cloud project

The Google Health API is enabled in the Google Cloud project **`fitbit-agent-503p`**. Its OAuth app
("Patterns 503P") is **External** and in **Testing** mode, with the account that owns the Fitbit
data added as a test user and four read-only scopes: `googlehealth.activity_and_fitness`,
`googlehealth.health_metrics_and_measurements`, `googlehealth.sleep`, `googlehealth.nutrition`.
The OAuth client is of type **Desktop app**; its ID and secret live only in `.env`. These scopes
are restricted: publishing would need Google verification and a security assessment, so the app
stays in Testing (at most 100 test users; sign-ins expire after 7 days and need `connect` again).
To let someone else sign in, add their Google account as a test user in the console.

### Data on disk (all git-ignored)

| Path | What |
|---|---|
| `Takeout/` | first export (2026-06-27 to 2026-10-15), legacy layout with `Global Export Data` |
| `data/raw-2026-10-21/` | second export: no `Global Export Data`, sleep in `UserSleeps*` (v1 and v2 algorithms), nutrition values all "N/A" |
| `data/google_token.json` | the Google sign-in (mode `0600`) |
| `takeout-*.zip` | the original downloads |

## Decisions and findings

- **Live API is the data source going forward**; Takeout stays as an offline import.
- **Never mix sources in one history.** The API's sleep is Google's v2 algorithm; the legacy
  export's is v1, about 38 minutes a night apart. Daily metrics are stored per source.
- **The API lacks** readiness, Fitbit's sleep score and cardio load; its sedentary periods do not
  reproduce Fitbit's sedentary total, so that column is left out. The recovery score uses sleep
  minutes and efficiency instead of Fitbit's sleep score.
- **Nutrition values exist only through the API** (34 nutrients plus energy and macros), arriving
  twice: Cronometer's daily total and per-entry Apple Health copies. Deduplicate before summing.
- **Recovery is our own score**, modeled on Bevel's inputs; a morning "how do you feel" check-in
  is the ground truth for comparing it with Fitbit's readiness.
- **Agent shape:** a cheap router (Jev, a typed classifier) sends each question to a specialist
  (sleep, recovery, activity, later nutrition); cross-domain questions are led by the owner of the
  metric asked about, which consults the others as tools. Whether this beats one general agent is
  measured. See [product.md](product.md).
- **Platform:** OpenAI for the LLM; Railway (backend and Postgres) and Vercel (web) when deploying;
  Langfuse for agent traces and Prometheus/Grafana for API metrics; iOS TestFlight undecided.

## Next

The approved plan, with the decisions from the 20-question session and the schedule, is in
[roadmap.md](roadmap.md). In short: **Sprint 1 (Oct 22–28)** builds the agent end to end (LLM
layer with a scripted fake, agent tools, general agent with the hypothesis loop and verifier,
four experts with consult and the router, memory, live data and the agent served to the app);
**Sprint 2 (Oct 29–Nov 4)** adds the recovery score, check-in, nutrition, daily runs, reminders
and experiments, tracing, accounts, deployment and the first evaluation; November after that is
buffer and hardening.

Sprint 1 so far: LLM layer, agent tools, general agent, verifier, human-readable findings and the
experts with consult, and the router are done. The memory and context design (kinds, scope, lifetime, retrieval, write path, injection
defenses, evaluation) is in [architecture.md](architecture.md#memory-and-context-designed-not-built).
Next, in order: the context builder (chat history and attachments); then the memory tables and write path; then live data and the agent
served through the API to the app.
