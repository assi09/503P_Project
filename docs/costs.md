# Model and API costs

The project runs on small prepaid budgets: **about $5 on OpenAI and $5 on TypeSafe (Jev)**. Treat
every paid request as spending real money that cannot be topped up casually.

## Rules

- **Tests and CI never call a paid API.** They use `ScriptedLLM` and fake HTTP transports.
- **Real runs only when model behaviour is what changed**, and as few as possible: one or two per
  pull request, on synthetic data unless the real data is the point. Never loop real runs.
- **Report the cost of every real run** (in the PR and in the log below). `AgentResult.budget`
  and `trace_json` give model calls, tool calls and dollars.
- **Free calls first**: listing models (`GET /v1/models` on both APIs) checks a key without
  spending anything.
- Every run has a `Budget` (default 12 model calls, $0.05); raise it only on purpose.
- `FA_LLM_SPEND_CAP_USD` (set to 4 in `.env`) refuses calls once reached. **It is counted per
  process for now**, so it does not add up across commands; until spending is recorded in the
  database (planned with tracing), keep the log below current by hand.

## Estimated cost per request

Measured on 2026-10-21 where noted; otherwise from published prices.

| Request | Model | Estimate |
|---|---|---|
| Daily check when nothing changed | none: the screen is deterministic | $0 |
| Investigating a change (general agent) | `gpt-5.4-mini` | ~$0.02–0.03 (measured: $0.024, 8 model calls, 14 tool calls, 27 s) |
| Simple chat question | `gpt-5.4-mini` | ~$0.005–0.01 |
| Expert answer, quick, no consult | `gpt-5.4-mini` | ~$0.01 (measured: $0.0086–0.0134, 4–6 model calls, about 10 s) |
| Expert answer with a consult | `gpt-5.4-mini` | ~$0.02 (measured: $0.0169–0.0261, 7–11 model calls, about 19 s) |
| Write-up with the large model, one call | `gpt-5.5` | ~$0.04–0.05 |
| Routing one question | Jev | ~$0.00003 (measured: topic plus four yes/no questions, median 0.21 s) |
| Checking one answer for advice | Jev | ~$0.00004 (4 to 5 sentences per call) |

Prices used for cost accounting are in `backend/app/agent/llm.py` (`PRICES`; per million tokens:
`gpt-5.4-mini` $0.75 in / $4.50 out, `gpt-5.5` $5 / $30). The model list on 2026-10-21
confirmed `gpt-5.4-mini`, `gpt-5.4`, `gpt-5.4-nano` and `gpt-5.5` are available to the key.
TypeSafe's model list (`jev-latest`, `jev-preview`) has no prices; the Jev estimate uses the
published $0.042 per million input tokens, output free.

## Budget plan to the demo (OpenAI, about $3 of $5)

| Use | Estimate |
|---|---|
| Development real runs (1–2 per PR) | ~$1 |
| One full evaluation: ~20 synthetic scenarios × 3 model-based setups | ~$1.50 |
| Router comparison: 100 labeled questions (Jev ~$0.003, LLM router ~$0.10) | ~$0.10 |
| Demo rehearsal | ~$0.25 |

Larger evaluation and user-testing runs in the final week need a top-up, decided then.

## Spend log

| Date | What | Cost |
|---|---|---|
| 2026-10-21 | OpenAI and TypeSafe model lists (key checks) | $0 |
| 2026-10-21 | First real investigation, synthetic person (sleep drop with later bedtime) | $0.024 |
| 2026-10-21 | Readable findings check, same synthetic person (3 model calls, 10 tool calls) | $0.0096 |
| 2026-10-23 | Recovery expert, deep, synthetic person (4 model calls, 22 tool calls; all claims rejected: ids in the text) | $0.0217 |
| 2026-10-23 | Sleep expert, deep, same person after the fix (7 model calls, 16 tool calls; 3 verified claims, no consult) | $0.0152 |
| 2026-10-23 | Sleep expert, deep, after listing other experts' metrics (10 model calls, 17 tool calls; consulted recovery, 4 verified claims) | $0.0247 |
| 2026-10-23 | Jev routing checks, 16 made-up questions: topic only (14/16), then topic and per-expert needs (16/16 on the lead, 14/16 exact), 50 calls in all | $0.0013 |
| 2026-10-23 | Routed answer end to end, quick, synthetic person: Jev led with recovery and consulted sleep; all claims rejected (display names in the claims' metric field) | $0.0204 |
| 2026-10-23 | Same after the name fix: routing right again, 0 claims (null result written as an association; the consult's tool calls all refused by a budget bug) | $0.0207 |
| 2026-10-23 | Same after both fixes: 4 verified claims, consult used | $0.0188 |
| 2026-10-23 | Consult policy A vs B: 4 questions × 2 variants × 2 runs ([experiments.md](experiments.md#consult-policy-a-vs-b-2026-10-23)) | $0.2435 |
| 2026-10-23 | Verifier metric check: sleep expert asked about HRV, no consult (4 verified claims) | $0.0081 |
| 2026-10-23 | Follow-up routing, 8 conversations × 2 settings, Jev | $0.0005 |
| 2026-10-23 | Two-turn conversation end to end (sleep, then "What about on weekends?") | $0.0156 |
| 2026-10-23 | Advice guard on the 32-sentence set, Jev | $0.0002 |
| 2026-10-23 | Two-turn conversation again with the guard on (OpenAI $0.0197, Jev guard $0.0001) | $0.0198 |
