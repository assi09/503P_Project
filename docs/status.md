# Project status

The page to read first when picking the project up. Updated 2026-10-21.

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
| Analysis | deterministic tools returning `Evidence`; 14-vs-28-day screen with FDR correction and a templated report (the no-LLM baseline) |
| API | `/health`, `/data/status`, `/reports/latest`, `/evidence/{id}`; single user, reads Takeout, no auth |
| App | Today, Ask (expert picker, quick/deep, attachments, routed answers on mock data), Reminders, Data; Expo SDK 57, runs in Expo Go and on the web |
| Engineering | protected `main`, PRs with both CI jobs required, ~160 backend and ~50 mobile tests |

**Not built yet:** the agent (router, experts, verifier, memory), the recovery score, nutrition
columns, the API serving live data, accounts, deployment, tracing and metrics, the evaluation
suite, the failure matrix and threat model.

## Local setup

1. Backend: `python3 -m venv .venv && source .venv/bin/activate && pip install -e "backend[dev]"`.
2. Database: `docker compose up -d db` (Postgres on port **5433**), then
   `alembic -c backend/alembic.ini upgrade head`.
3. `.env` at the repository root (git-ignored; copy `.env.example`): `FA_TIMEZONE`,
   `FA_EXPORT_DIR`, and `FA_GOOGLE_CLIENT_ID` / `FA_GOOGLE_CLIENT_SECRET` for live data.
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

1. **The agent**, built behind an LLM interface with a scripted fake for tests: tools wrapping the
   analysis, the investigation loop, the verifier, then the router and experts. Needs an OpenAI key
   in `.env` only for real runs.
2. The API serving live data from the database; "Sync now" and sync status in the Data tab.
3. Nutrition columns (deduplicated) and the nutrition expert.
4. Recovery score and the morning check-in.
5. Evaluation suite, tracing and metrics, accounts, then deployment.

The detailed plan is in [roadmap.md](roadmap.md).
