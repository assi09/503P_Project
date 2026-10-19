# Roadmap

The plan from here to the demo (around the end of November 2026). Each item ships as its own pull
request. **Status: saved, not started**: the current focus is the app's UI redesign. Work on these
milestones starts only when the team decides to.

The agent is built behind an LLM interface and tested with a scripted fake LLM; a real OpenAI key
is only needed for real runs and the full evaluation. No cloud deployment for now: everything
runs locally with Docker Compose.

## M1: data and accounts

- **Synthetic Fitbit Air exports:** write synthetic people out as complete Google Health Takeout
  folders in the real Fitbit Air layout, with a manifest of the changes planted in each, so the
  whole pipeline is tested against known answers.
- **Database:** Postgres with Alembic migrations (SQLite in tests) for users, imports, daily
  metrics, evidence, reports, chat, context answers, reminders and agent runs.
- **Accounts:** email and password with short-lived tokens; every endpoint only sees the signed-in
  user's data.
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
  rejections), metrics endpoint, cost per successful task.

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

## M5: hardening and documentation

- Rate limits, CodeQL and Dependabot, an end-to-end browser test in CI.
- Failure matrix, threat model, API documentation, evaluation results, reproduction guide.

## M6: demo

- A demo script that includes edge cases, a tagged release (`v1.0-demo`) and the poster.

## After the demo

- Google sign-in and live Google Health sync.
- Cloud deployment.

## Inputs needed

- An OpenAI API key in a local `.env` before the full evaluation (around November 10).
- Whether friends' Fitbit Air exports will be collected for the real-data audit.
