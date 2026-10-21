# Roadmap

The plan from here to the demo (around the end of November 2026). Each item ships as its own pull
request. Current state and decisions: [status.md](status.md). Last updated 2026-10-21.

**Priority: the agent (M2) and its evaluation (M4).** They carry most of the grade. The agent is
built behind an LLM interface and tested with a scripted fake LLM; a real OpenAI key is only needed
for real runs and the full evaluation. The instructor requires full deployment: it follows once the
agent's core loop works (M5), not at the very end.

## M1: data and accounts

- **Done:** live Google Health sign-in, API client and mapping to the daily table, verified against
  Takeout; Postgres with the first migration; `python -m app.sync pull` stores live days.
- **Serve live data:** the API reads the daily table from the database instead of Takeout; "Sync
  now" and sync status in the Data tab.
- **Nutrition columns:** daily energy, macros and key nutrients from the API, deduplicated between
  Cronometer's daily total and its per-entry copies.
- **Synthetic Fitbit Air exports:** write synthetic people out as complete Google Health Takeout
  folders in the real Fitbit Air layout, with a manifest of the changes planted in each, so the
  whole pipeline is tested against known answers.
- **Database, continued:** tables for evidence, reports, chat, check-ins, context answers,
  reminders and agent runs, each added by migration with the feature that needs it.
- **Accounts:** email and password with short-lived tokens; every endpoint only sees the signed-in
  user's data. Google sign-in per user (token encrypted in `google_connections`) once the backend
  has a public HTTPS address.
- **Takeout upload:** safe zip handling (size limits, zip-bomb and path-traversal checks, only
  health folders read) and ingestion into the user's account.

## M2: the agent

- **LLM interface:** an OpenAI client with timeouts, retries and cost accounting, plus a scripted
  fake for tests.
- **Tools:** validated wrappers around the analysis tools, plus change-point detection and a
  weekday/weekend split. The model only chooses metrics and windows; data access stays
  server-side.
- **Loop:** screen, form hypotheses, investigate with tools within a budget, draft claims, verify,
  publish. It asks the user when a change has no explanation in the data.
- **Verifier:** every claim cites evidence and its numbers and directions are checked
  deterministically; claims that fail are repaired once, then dropped. Medical advice is rejected.
- **Memory:** the user's answers and past findings inform the next run; follow-up checks.
- **API and app:** reports, chat and context questions served by the agent.

## M3: reminders and AgentOps

- Reminder proposals, approvals and settings stored on the server; approved reminders delivered as
  local notifications respecting quiet hours and the daily limit.
- Tracing of every run and tool call (latency, tokens, cost, retries, failures, verifier
  rejections) in Langfuse; API metrics in Prometheus and Grafana; cost per successful task.

## M4: evaluation

- Scenario suite on synthetic people (single changes, a change explained by another, confounders
  such as low wear, people with no change, short histories), split into development and held-out
  sets.
- Baselines: statistics-only report, LLM without tools, agent without verifier, full agent.
- Metrics: finding precision and recall, cause attribution, unsupported-claim rate, abstention,
  questions asked, latency and cost.
- Adversarial tests (prompt injection, medical questions, cross-user access, malicious uploads,
  model failures), each failure turned into a regression test; a deterministic eval gate in CI.
- Audit on real exports.

## M5: deployment, hardening and documentation

- Deployment: backend and Postgres on Railway, the web app on Vercel, Android builds with EAS
  (iOS TestFlight if an Apple Developer account is set up), deploys from `main` after CI passes.
- Rate limits, CodeQL and Dependabot, an end-to-end browser test in CI.
- Failure matrix, threat model, API documentation, evaluation results, reproduction guide.

## M6: demo

- A demo script that includes edge cases, a tagged release (`v1.0-demo`) and the poster.

## After the demo

- Publishing the Google OAuth app (verification and security assessment) so anyone can sign in.

## Inputs needed

- An OpenAI API key in a local `.env` before the full evaluation (around November 10).
- Whether friends' Fitbit data will be collected (as Google test users) for the real-data audit.
