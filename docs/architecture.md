# Architecture

This document covers the parts of the design that are settled. Components marked *planned* are
not implemented yet.

## Principle

The agent decides **what to investigate**; deterministic code does **all the computing and checking**.
Every statement in a report or chat answer must cite an `Evidence` record produced by a tool, and a
verifier rejects statements it cannot match to one.

## Components

```
 Mobile app (planned) ── HTTPS + auth ──► API (planned)
                                            │
          ┌─────────────────────────────────┼──────────────────────────────┐
          ▼                                 ▼                              ▼
   Ingestion                         Agent (planned)                  Storage (planned)
   Takeout export ─► daily table     investigation loop               per-user daily metrics,
          │                          over analysis tools              evidence, reports, memory
          ▼                                 │
   Analysis tools ◄──── tool calls ─────────┘
   (deterministic) ──► Evidence ──► Verifier (planned) ──► report / answer
```

| Component | Location | Status |
|---|---|---|
| Takeout ingestion | `backend/app/ingest/takeout.py` | done |
| Analysis tools and `Evidence` | `backend/app/analysis/` | describe, coverage, compare_windows, trend, correlate |
| Screen and templated report (the no-LLM baseline) | `backend/app/analysis/screen.py`, `report.py` | done |
| Synthetic data with planted effects | `backend/app/synthetic.py` | done |
| Agent, verifier, memory | `backend/app/agent/` | planned |
| API | `backend/app/api/` | `/health`, `/data/status`, `/reports/latest`, `/evidence/{id}`; single user, no auth yet |
| Mobile app | `mobile/` | planned |
| Evaluation suite | `eval/` | planned |

### Ingestion

Reads a Google Takeout ("Google Health") export into one row per local calendar day and one column
per metric (see [metrics.md](metrics.md) for every column and its Fitbit source). Intraday data is
bucketed by the user's timezone; profile and account files are never opened. Malformed exports
raise `IngestError` instead of producing partial data silently.

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

A single agent, not a multi-agent system. It screens the data for changes, forms hypotheses about
*why* a metric changed (for example a bedtime shift, an activity change, or a data-quality problem
such as low wear time), chooses which tools to run to test them, and stops when the hypotheses are
resolved or its budget is spent. It never computes statistics itself.

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
are never committed. Tests and evaluation use the synthetic generator, whose baselines are generic
values, not taken from any real export.
