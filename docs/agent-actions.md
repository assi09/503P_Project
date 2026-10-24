# Agent-assisted logging: tools and intent

Planned core capability, agreed 2026-10-24. Build locally first. Food photos remain part of the
intended demo, with editable estimates and provenance. Workout and food logging come first;
hydration is feasible and retained as a later small extension, not a prerequisite. Choose tools
for problems people actually bring to the agent, then evaluate task completion.

## Who decides

Use a hybrid: **Jev classifies; experts prepare; deterministic code authorizes and executes**.
The router keeps topic and request intent separate, in the same Jev call. Nutrition-related input
must not automatically become a food record. The Activity and Nutrition experts select relevant
read tools, ask for missing details and propose a structured draft. The app shows the exact
payload for review. Only an authenticated confirmation of that version can authorize a write.
Neither a classifier label, a tool argument nor a conversational "yes" is execution permission.

| Message (synthetic example) | Intended behavior |
|---|---|
| "How much protein did I eat yesterday?" | Read/compute and answer with evidence; no draft or write. |
| "Log lunch: chicken and rice." | Prepare a draft; ask for time/serving and unresolved food details. |
| "I had chicken and rice." | Clarify whether the person wants to log it or ask about it. |
| "Log lunch and compare my protein with yesterday." | Draft the log and answer the read question separately; unconfirmed food is excluded from the historical total. |
| "Here is a photo of lunch." | Clarify the request; do not infer consent to log. |
| "Undo the last meal." | Resolve the owned entry, show the requested deletion, obtain confirmation, then execute. |
| "Yes" after earlier logging questions | Resolve against a server-held draft; never inherit approval from chat history. |

Intent choices: `read`, `log`, `mixed`, `manage` (edit/cancel/undo), `clarify`. Low confidence means
clarify. The initial 0.7 threshold is provisional, not a measured guarantee. Scope refusal still
wins over any intent or expert selection. When Jev fails, a deliberately narrow keyword rule can
recognise explicit requests; ambiguous statements and follow-ups remain unclear. This is not a
security boundary. Proposal eligibility also needs the current message, owned draft state and
server-side validation, not just the inferred intent.

**Implemented first slice:** `backend/app/agent/intent.py`, router integration (Jev, keyword and
LLM baseline), intent probabilities and decision in the answer trace, and fake-service tests.
Intent is currently observational: existing answer dispatch is unchanged, and no proposal UI,
action storage or Google writes are enabled by this change. Do not describe logging as working.
The next slice is a persistent proposal lifecycle and confirmation API before exposing draft tools.

## Tools to build around user tasks

Names below are proposed capabilities, not existing public API contracts.

| User problem | Tool/capability | Why and boundary |
|---|---|---|
| Understand existing intake | Nutrition history, coverage, compare/trend tools | Finish API nutrition mapping and deduplication; missing data is not zero. |
| Find the food they ate | `find_food`, `get_food`, available serving units | Google food records first; keep candidate IDs, source and serving basis. Confirm ambiguous matches. |
| Adjust a known serving | `scale_nutrients` | Pure unit/serving arithmetic over fetched or user-supplied values; never model arithmetic. Do not convert cups/pieces to grams without a food-specific conversion. |
| Record a meal with known numbers | `propose_food_log` | Preserve supplied energy/macros and missing values. A missing macro is not zero; calorie estimates do not independently verify user input. |
| Record a workout | `propose_workout_log`, existing-session lookup | Resolve time, type and duration; inspect overlap with device sessions before creating another entry. |
| Understand a workout window | `summarize_workout` | New intraday fetch plus deterministic sample coverage, HR/steps summaries; avoid extrapolating from daily totals or across gaps. |
| Record an entry from a photo | `estimate_food`, then food lookup and a draft | Extract candidate foods/portion assumptions; ask about hidden ingredients, amount or preparation when needed. Show uncertainty and allow editing. No invented precision. |
| Fix a draft | `get_draft`, `revise_draft`, `cancel_draft` | Owned server state; revision invalidates prior confirmation. Cancellation before execution makes no remote write. |
| Apply or undo a reviewed action | Confirmed executor, provider reconciliation, delete | Server-controlled operations, absent from the model's unrestricted toolbox. Durable status, IDs and audit; retry only when outcome is known. |
| Record water | `propose_hydration_log` | Later extension using the same approval path, with explicit volume units. |

Start with Google food lookup because the app already connects to Google and its nutrition guide
prefers identified foods. Prototype actual lookup and serving coverage before promising that its
catalogue will find every local dish. USDA FoodData Central is a candidate fallback with food
search and detail endpoints, a separate API key and public-domain data. It does not remove the
need to disambiguate recipes or portions. Do not add another provider until catalogue coverage
shows it is useful. Persist provider IDs and provenance rather than copying a model's recalled
nutrient values. No browsing or arbitrary URL-fetch tool is needed in the agent's runtime.

## Provider findings and corrections to the initial discussion

Research checked 2026-10-24 using primary documentation, without reading personal records:

- Google supports creating workout sessions, nutrition logs and hydration logs with their
  respective write scopes. Request only the capability the person enables; do not expand every
  existing read-only connection automatically. Testing-mode console configuration remains a
  separate manual setup task, not something this research proves for the deployed OAuth client.
- Food and food measurement units are read-only catalogue resources. Identified-food logs refer
  to a food ID and serving; custom/anonymous-food logs supply the nutrient values.
- **Anonymous-food logs are not editable after creation**, according to Google's nutrition guide.
  All drafts can be edited before confirmation. Post-write correction may require a separately
  confirmed replacement/deletion flow; do not promise arbitrary in-place editing or silently
  delete and recreate an entry.
- Create returns an **Operation**, not necessarily a finished DataPoint. Track the returned
  operation and actual completion/error before declaring success or persisting a provider ID as
  confirmed. Batch delete also returns an Operation. A successful HTTP status alone is insufficient.
- The documented create method does not expose a request-id parameter. Do not assume provider
  idempotency. Persist a local execution claim, reconcile ambiguous outcomes and prevent blind
  retry; exactly-once effects during network failure are not established by this documentation.
- Workouts have an interval, exercise type, active duration and optional summary metrics. Raw
  telemetry uses separate data types. Do not write fabricated sensor measurements, mark a manual
  log as sensor-measured, or add a workout summary to daily totals a second time.
- The nutrition examples use kcal for energy and grams for nutrient quantities, including
  sodium. Unit conversion is deterministic and tested; do not send milligrams as grams.

Sources: [Google nutrition/hydration guide](https://developers.google.com/health/data-types/nutrition),
[workout guide](https://developers.google.com/health/data-types/workouts),
[create method](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/create),
[batch delete](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/batchDelete),
[USDA API guide](https://fdc.nal.usda.gov/api-guide/).

## Implementation and evaluation sequence

1. Intent routing and a task-based tool plan (this slice). Scripted tests cover independent topic
   and intent, read-only questions, ambiguous meal/photo statements, mixed requests, explicit
   cancellation/undo, malformed classifier outputs, fallback and medical refusal.
2. Durable owned drafts, versioning, confirmation, cancellation, execution claims and audit, with
   migration and additive backend/mobile contract. Fake provider exercises concurrency, restart
   and ambiguous outcomes before any model can propose a remote action.
3. Workout and supplied-value food proposals and clarification in chat, with review cards and
   local fake-provider execution. Logging must work even when an expert has no historical data.
4. Google capability consent, actual writes/undo, operation completion, intraday summary evidence,
   nutrition sync and duplicate reconciliation. Real account writes need explicit approval of
   the exact test record and cleanup.
5. Photo input and estimates via the same drafts: consent, validation, retention/deletion, no
   photos in logs, no estimated values represented as measured statistical Evidence. One or two
   paid synthetic-image checks only when model behavior needs verification, logged in costs.
6. Held-out task evaluation: completion/clarification, read-only false-action proposals, ownership
   and unauthorized execution, duplicates, numerical/unit correctness, undo/recovery, cost and
   latency. Compare hybrid routing with expert-only intent decisions before claiming Jev wins.
   Include negation, multiple requests, stale drafts, changed topics and injection in food names.

No approval text is trusted from a photo, food name, imported entry, prior chat message or model.
Proposed actions are not memory facts; their storage, lifecycle and retention need their own rules.
