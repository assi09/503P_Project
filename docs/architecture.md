# Architecture

This document covers the parts of the design that are settled. Components marked *planned* are
not implemented yet.

## Principle

The agent decides **what to investigate**; deterministic code does **all the computing and checking**.
Every statement in a report or chat answer must cite an `Evidence` record produced by a tool, and a
verifier rejects statements it cannot match to one.

## Components

```
 Mobile app (Expo) ──── HTTPS (+ auth, planned) ────► API (FastAPI)
                                                       │
     ┌──────────────────────┬──────────────────────────┼─────────────────────────┐
     ▼                      ▼                          ▼                         ▼
 Google Health API     Takeout export          Agent (planned)             Postgres
 (live sync) ──┐       (offline import) ─┐     router → experts            users, daily metrics,
               ▼                         ▼     over analysis tools         sync runs; later reports,
          daily table (same columns from either source)                    chat, memory, traces
               │                                   │
               ▼                                   ▼
        Analysis tools (deterministic) ──► Evidence ──► Verifier (planned) ──► report / answer
```

| Component | Location | Status |
|---|---|---|
| Takeout ingestion | `backend/app/ingest/takeout.py` | done (legacy layout; newer exports lack `Global Export Data`) |
| Google Health sign-in | `backend/app/sync/google_auth.py` | done: loopback OAuth, token file `0600`, one local user |
| Google Health API client | `backend/app/sync/client.py` | done: paging, roll-up windows, retries |
| API data → daily table | `backend/app/sync/daily.py` | done, verified against Takeout ([metrics.md](metrics.md#from-the-google-health-api)) |
| Database | `backend/app/db/`, `backend/migrations/` | users, Google connections, daily metrics, sync runs |
| Live data → database | `backend/app/sync/pull.py` | `python -m app.sync pull`; the API service still reads Takeout |
| Analysis tools and `Evidence` | `backend/app/analysis/` | describe, coverage, compare_windows, trend, correlate |
| Screen and templated report (the no-LLM baseline) | `backend/app/analysis/screen.py`, `report.py` | done |
| Synthetic data with planted effects | `backend/app/synthetic.py` | done |
| Agent, verifier, memory | `backend/app/agent/` | planned: **the next major piece** |
| Recovery score | `backend/app/analysis/` | planned, see [product.md](product.md#recovery-score) |
| Router and experts | `backend/app/agent/` | planned, see [product.md](product.md#routing) |
| API | `backend/app/api/` | `/health`, `/data/status`, `/reports/latest`, `/evidence/{id}`; single user, no auth yet |
| Mobile app | `mobile/` | Today, Ask (expert picker, depth, attachments), Reminders, Data; mock data where the API has no endpoint |
| Evaluation suite | `eval/` | planned |

### Ingestion

Reads a Google Takeout ("Google Health") export into one row per local calendar day and one column
per metric (see [metrics.md](metrics.md) for every column and its Fitbit source). Intraday data is
bucketed by the user's timezone; profile and account files are never opened. Malformed exports
raise `IngestError` instead of producing partial data silently.

### Live sync (Google Health API)

The Fitbit data comes live from the Google Health API (v4). Sign-in is Google's loopback OAuth
flow for desktop apps, with four read-only scopes (activity and fitness, health metrics, sleep,
nutrition); the refresh token is stored in `data/google_token.json`, readable only by its owner.
The Google Cloud project's OAuth app stays in **Testing** mode, because health scopes are
restricted: only listed test users can sign in, and Google expires the sign-in after 7 days, which
surfaces as `ReconnectNeeded`. Per-user sign-in from the phone needs the backend on a public HTTPS
address and arrives with accounts and deployment.

The client lists data points across pages and fetches daily roll-ups in the windows the API
accepts; rate limits, server errors and network failures are retried with backoff. The mapping
fills the same columns as Takeout, so everything downstream is source-independent, with one rule:
**a history comes from one source**. The API's sleep is Google's current algorithm, the legacy
export's is the old one (about 38 minutes a night apart), so mixing them would fake a change.

### Storage

Postgres (Docker locally, managed when deployed), schema changes as Alembic migrations, SQLite in
tests. Daily metrics are stored one row per user, source, day and metric, so new metrics (such as
nutrition) need no migration. Every table holding a person's data has a `user_id`, and every query
filters on it. Tables for later features are added by migration when the feature is built.

### Analysis tools

Pure functions over the daily table. Each validates its arguments (`ToolError` on bad input),
computes on non-missing days only, and returns an `Evidence` record with:

- a unique `id` that claims cite,
- the tool name, metrics and date windows used,
- the sample size `n` and a `sufficient` flag (false below a per-tool minimum number of days),
- the computed statistics.

Methods are chosen for short, noisy personal data: Mann-Whitney U with Cliff's delta for window
comparisons, Theil-Sen slopes with Kendall's tau for trends, and Spearman correlation across lags
with a Bonferroni adjustment for the lags tried.

### Screen and report

The screen compares the last 14 days of every metric with the 28 days before (Mann-Whitney U,
Cliff's delta), leaving low-wear days out of activity totals. Because about twenty metrics are
tested at once, p-values are adjusted with Benjamini-Hochberg (FDR 5%), and only changes with at
least a medium effect are reported. The adjusted p-value is stored in the evidence, so the app
shows the value the decision was made on. The report turns each change into templated text whose
numbers all come from its evidence. It is what the app shows until the agent exists, and the
"statistics only" baseline the agent is evaluated against.

### Agent (planned)

A router and specialist experts (sleep, recovery, activity, later nutrition), each owning a set of
metrics; see [product.md](product.md#experts) for the split and how cross-domain questions are
handled. An expert screens its metrics for changes, forms hypotheses about *why* a metric changed
(for example a bedtime shift, an activity change, or a data-quality problem such as low wear
time), chooses which tools to run to test them, and stops when the hypotheses are resolved or its
budget is spent. It never computes statistics itself. Whether the split beats a single general
agent is measured, not assumed.

### Verifier (planned)

Deterministic. Each claim must reference evidence ids; directions and numbers in the claim are
checked against the stored statistics, and claims built on insufficient evidence are rejected.

## Boundaries

| Agentic | Deterministic | Human-controlled |
|---|---|---|
| choosing what to investigate, forming and testing hypotheses, writing findings | ingestion, statistics, verification, authorization, data access | confirming context the data cannot show, approving consequential actions, acting on insights |

The agent describes patterns in the user's own data. It does not give medical diagnoses or advice.

## Data and privacy

The repository is public. Personal exports live under `data/` or `Takeout/`, both git-ignored, and
are never committed; so are `.env` (the OAuth client ID and secret) and the Google sign-in token
in `data/`. The LLM will only ever receive aggregated statistics, never raw rows or account data. Tests and evaluation use the synthetic generator, whose baselines are generic
values, not taken from any real export.
