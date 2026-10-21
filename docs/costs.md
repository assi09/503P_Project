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
| Expert answer with a consult | `gpt-5.4-mini` | ~$0.01–0.03 |
| Write-up with the large model, one call | `gpt-5.5` | ~$0.04–0.05 |
| Routing one question | Jev | ~$0.00001–0.00003 |

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
