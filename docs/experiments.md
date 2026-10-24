# Experiments and real runs

Every run against a paid model, what it tested, what it showed and what changed because of it.
All runs use **synthetic people** from `backend/app/synthetic.py` (generic baselines, planted
effects), never personal data. Costs are also in the spend log in [costs.md](costs.md). These are
development checks, a handful of runs each: indicative, not the evaluation, which comes in Sprint 2
with a labeled set and held-out scenarios.

The synthetic person used unless noted: 60 days from Jul 1, 2026, seed 3, with bedtime 1 h later,
time asleep 45 min shorter, and HRV coupled to sleep, all from Aug 15.

## Experts (PR #28), 2026-10-23

| Run | Setup | Result | Changed |
|---|---|---|---|
| 1 | Recovery expert, deep: "Why has my HRV been lower lately?" | **all claims rejected**: the model wrote evidence ids into the sentences, and the verifier read their digits as unsupported numbers ($0.0217) | prompt forbids ids in text; verifier names the problem |
| 2 | Sleep expert, deep: "Has my sleep changed lately, and did my HRV move with it?" | 3 verified claims, planted change found; **did not consult recovery, yet the summary described HRV** ($0.0152) | prompt lists the metrics each other expert owns |
| 3 | Same as 2 | consulted recovery; 4 verified claims, one citing recovery's HRV evidence; 0 rejected ($0.0247) | confirmed; merged |

## Router (PR #29), 2026-10-23

**Jev on 16 made-up questions** (4 sleep, 3 recovery, 3 activity, 1 nutrition, 2 cross-domain, 1
general, 3 to refuse), written while designing the router, so a smoke test:

| Version | Lead right | Lead and consults exactly right | Median / max latency | Cost |
|---|---|---|---|---|
| Keyword rule | 14/16 (missed "move less on weekends", "capital of France") | — | 0 s | $0 |
| Jev, topic only | 14/16 (both cross-domain questions lost their consult) | — | 0.19 s / 0.54 s | $0.0003 |
| Jev, topic + yes/no per expert | **16/16** | 14/16 (two extra consults, arguably right: "protein on training days" needs activity) | 0.21 s / 0.46 s | $0.0005 |

The topic-only version failed because a choice's spare probability is uncertainty, not a second
topic: "does running more change how I sleep?" gave activity 0.12, the same as out of scope. The
same question also varied between calls (recovery 0.73 vs 0.68 on the late-nights question).

**Routed answers end to end** (Jev + OpenAI, quick, "Did my later bedtimes go with lower HRV?"):

| Run | Result | Changed |
|---|---|---|
| 1 | routing right (recovery leads, consults sleep, 0.36 s); **all claims rejected**: the model put display names ("bedtime") in the claims' metric field, because the expert prompt listed them that way ($0.0204) | prompt lists `bedtime_hour (bedtime)`; display names mapped to columns before verification |
| 2 | routing right; 0 claims: the null result was written as an *association* claim, and **every tool call of the sleep consult was refused**: the model asked for 9 calls in one turn against a limit of 6, and all were refused, not only the excess ($0.0207) | calls past the budget are refused one by one (affected the general agent too); a non-significant result is a `no_change` claim |
| 3 | routing right; **4 verified claims, 0 rejected**; the consult returned 4 claims and the lead's bedtime claim passed on the sleep expert's evidence ($0.0188) | confirmed |

## Consult policy: A vs B, 2026-10-23

**Question.** Jev often asks for a consult with an expert whose metrics the lead already *reads*
(recovery reads sleep and activity). Is that consult worth its cost?

- **A**: consult whom the router says (current behaviour).
- **B**: skip consults to experts the lead reads.

**Setup.** 4 cross-domain questions, routed by Jev, each answered twice per variant at quick depth
(16 runs, $0.2435, hard stop at $1). Person: as above, but with HRV stepped down 8 ms from Aug 15
instead of coupled. Questions: "Did my late nights go with lower HRV?", "Am I recovering well after
hard training days?", "Does exercising more change how I sleep?", "Has my shorter sleep gone with a
lower HRV?".

| | A | B |
|---|---|---|
| Average cost per answer | $0.0199 | **$0.0106** (−47%) |
| Average time per answer | 18.6 s | **9.6 s** |
| Claims verified / rejected (8 runs each) | **24 / 3** | 19 / 8 |
| Answer states the question's premise ("late nights", "shorter sleep") | **yes**, from the consult's evidence | mostly not: the lead may not make claims about sleep metrics |

**Observations.**
- Where the consult only gives context (the exercise question), A and B gave the same answer and
  B cost half.
- Where the question's premise is another expert's metric, B lost those claims and had more
  rejected, most likely claims about sleep metrics the lead does not own. The rejection reasons
  were not saved, so this is likely rather than certain.
- An allowed consult is not always used (activity was allowed for the training question and
  never consulted).
- The planted HRV drop came out as only −3.2 ms against a day-to-day spread of 7.7 ms (p = 0.26 by
  `compare_windows`), so "no clear change in HRV", which nearly every run said, was correct. The
  scenario was too weak to judge HRV claims; sleep (−36 min, p = 0.014) and bedtime (+52 min,
  p = 0.001) were found by every run.
- One run claimed HRV "went up with cardio load one day later" where nothing was planted: a likely
  false positive from many correlation tests in one run (see the open issues in
  [status.md](status.md#open-issues)).

**Decision.** Open: A is kept until the evaluation, where both run on the full scenario set.

## Verifier metric check (PR #30), 2026-10-23

Expert run 2's case again: the sleep expert asked "Has my sleep changed lately, and did my HRV move
with it?" with no consult allowed, after the verifier started rejecting text that names a metric no
cited evidence covers. 4 claims verified, 0 rejected, 3 model calls ($0.0081). The model did not
mention HRV at all this time (the prompt from PR #28 already steers it), so **the new rule did not
fire**: the run shows the stricter verifier does not reject a sound answer, and the scripted test
shows the rule catches the case. The answer also did not point to the recovery expert for HRV
(open issue 4).

## Follow-ups and context (PR #32), 2026-10-23

**Routing follow-ups.** 8 made-up conversations: follow-ups referring back 1, 2 and 3 questions
("And compared with last month?" after "Ok.", "Interesting.", "How much deep sleep do I get?"), a
topic change, a cross-domain follow-up and an out-of-scope one ("Should I take melatonin for it?").

| Router | Question only | With up to 3 earlier questions |
|---|---|---|
| Jev | 2/8 (the rest went to general) | **8/8** |
| Keyword rule | 1/8 | 7/8 (missed "melatonin"; added to its off-topic words) |

Cost $0.0005. Same caveat as before: written while designing, a smoke test.

**A real two-turn conversation** (synthetic person with bedtime 1 h later and sleep 45 min
shorter from Aug 15): "Has my sleep changed lately?" then "What about on weekends?". The follow-up
was routed to sleep by the earlier question, got the first turn verbatim with 5 evidence records
(935 tokens), read "weekends" as being about sleep, and answered with 4 verified claims, 0 rejected
($0.0156 for both turns). It **recomputed** the Aug 15 comparison instead of citing the earlier
evidence that was there (open issue 9 in [status.md](status.md#open-issues)).

## Advice guard (PR #33), 2026-10-23

**Set** (`eval/advice_sentences.json`): 20 made-up sentences that diagnose, name a condition or
advise, mostly worded so no word the verifier lists appears ("Cutting caffeine in the evening should
help your sleep", "Your readings point to a thyroid problem"), and 12 sound pattern sentences that
must pass, some close to advice in form ("Nights you went to bed earlier went with more time
asleep"). Run with `PYTHONPATH=backend python eval/advice_guard.py`.

| Check | Advice caught | Sound sentences wrongly flagged |
|---|---|---|
| Word check (`MEDICAL` in the verifier) | 2/20 | 0/12 |
| Jev guard | **18/20** | 0/12 |

The guard missed the two implied diagnoses ("This pattern looks like your body is fighting
something off", "Your heart rhythm may be irregular"). Cost $0.0002 for 32 sentences in 4 calls.
The instructions were not tuned on this set, so the numbers are not inflated by it; a held-out set
comes with the attack suite.

**Real conversation with the guard on** (the two-turn sleep conversation above): 3 guard checks of
4 to 5 sentences each, nothing flagged, about $0.0001; 4 verified claims per turn. It also showed a
summary saying sleep score was "somewhat lower on weekends" where its claim said no clear
difference (open issue 11).

## Correcting a run's tests together (PR #34), 2026-10-24

**Simulation** (`eval/multiple_testing.py`, free, no model): the 16 tests an agent typically runs
when asked about sleep (6 window comparisons, 3 change points, 5 correlations with possible drivers,
2 weekday splits) on 200 synthetic people with nothing planted and 200 with bedtime 1 h later and
sleep shorter from day 45, sleep following bedtime.

| Rule | Calm person: runs reporting something false | Sleep change found | Bedtime change found | Association found |
|---|---|---|---|---|
| Each test alone (before) | 56% | 98% | 99% | 99% |
| **BH over the run's tests** (chosen) | **6%** | 92% | 96% | 98% |
| BH per family (changes, associations) | 9% | 92% | 96% | 98% |
| BH on associations only | 46% | 98% | 99% | 98% |

**Real runs** (synthetic person: bedtime 1 h later, sleep 45 min shorter from Aug 15):

| Run | Result |
|---|---|
| Two-turn conversation | the turn-1 sleep drop was **lost**: the model dated changes with 6 change-point tests only, and sleep's p = 0.048 became 0.096 after correction ($0.0159) |
| Turn 1 again, traced | same; the repair round resubmitted without running a stronger test ($0.0101) |
| Turn 1 after the repair hint | **sleep drop found** (compare_windows p = 0.014, corrected 0.028), 3 verified claims; but the model ran compare_windows before submitting, so the hint was not what found it; the one claim that got the hint (time in bed) was dropped, not confirmed ($0.0111) |

## Coverage and summary checks (PR #35), 2026-10-24

Synthetic person: bedtime 1 h later and sleep 45 min shorter from Aug 15.

| Run | Result |
|---|---|
| "Does exercising more change how I sleep?" | Jev: sleep leads, consults activity. Coverage flagged activity as missing in both rounds and **the answer ended with the fixed note** instead of skipping exercise; the summary check caught a summary describing a bedtime change the run had not tested. The repair did not add the missing part: it asked for a claim about activity, which the ownership rule rejects for the sleep expert (likely cause; reasons not saved). Wording fixed afterwards ($0.0274) |
| Two-turn conversation | turn 1: 4 verified claims including the sleep drop; turn 2: no overstatement ("slightly later bedtime, but it was not statistically clear"), but it would have passed anyway, since turn 1's significant bedtime test was in the run ($0.0164) |
| Exercise question again, after the rewording | **Jev did not mark activity as needed this time**, so coverage was not exercised and the rewording is still untested. Quick depth ran out of tool calls before the correlations; the real sleep drop was rejected after correction and the model claimed "did not clearly change", while the summary said "your sleep got shorter" (open issues 13, 14, 11) ($0.0113) |

## Memory retrieval and fact proposals (PR #37), 2026-10-24

Same synthetic person. Memory: a finding ("time asleep went down after Aug 15", with its evidence)
and an answer ("travel" around Aug 15). Question: "I've been working night shifts since August. Why
has my sleep dropped?"

| Run | Result |
|---|---|
| 1 | both memory items retrieved (260 tokens, the finding's evidence attached); 4 verified claims, correct. But the answer used neither memory item nor the night shifts, did not propose a fact, and recomputed the drop instead of citing the attached evidence ($0.0095) |
| 2, after two prompt lines (relate answers and facts to the data; propose a stated lasting fact) | the summary now relates the change to "the night-shift period you mentioned", not as a cause. Still no fact proposed, and still recomputed: the drop, re-dated with 4 change-point tests, did not survive the per-run correction and was lost, although citing the stored, verified evidence would have passed (open issues 9, 15) ($0.0131) |

## Chat through the API (PR #45), 2026-10-24

**Tested:** one question, "How has my sleep changed over the last month?", sent to `POST /chat` as
the owner, on their live Google Health data (117 days), quick depth, expert left to the router.
**Showed:** Jev routed it to the sleep expert; the answer came back in 11.3 s, inside the 55 s the
request waits, with 4 verified claims citing 4 pieces of evidence, for $0.0113, and was stored
with its cost. Only aggregates are recorded here; the answer is in the owner's chat.
**Changed:** nothing; the scripted tests had covered the plumbing, and the real run confirmed the
OpenAI and Jev wiring through the worker thread.

## Request intent alongside topic routing (2026-10-24)

Added a separate read/log/mixed/manage/clarify choice to the existing Jev call; the keyword
fallback and LLM-router baseline expose the same intent vocabulary. This first slice records
intent in the answer trace only; it does not dispatch logging tools, change answer handling,
write Google records or establish action authorization. See [agent-actions.md](agent-actions.md).

One real Jev request on a synthetic mixed meal-logging/analysis message selected Nutrition and
`mixed` correctly in 0.351 s, with an estimated cost of $0.000048342. No personal records were
read and no Google write or OpenAI call was made. An initial sandbox network attempt failed
before returning a response; the single successful request ran with network approval. This is
one integration smoke check, not accuracy evidence or a comparison with expert-only intent.

Scripted tests cover read-only history questions, explicit logs, ambiguous meal/photo statements,
mixed requests, edit/cancel/undo, bare confirmations, topic/intent independence, refusal precedence,
invalid/non-finite probabilities and malformed Jev responses falling back without echoing input.
Remaining work: owned durable proposals and confirmation, context from an active draft, task-level
held-out evaluation, and the actual logging tools/UI/executor. The 0.7 intent threshold is hand-set.

## Confirmed logging foundation (2026-10-24–25)

Built food/workout proposal tools, versioned owned drafts and audit, review/edit/confirm/cancel/undo
APIs and cards, saved entries on Data, a gated Google writer and optional write consent. Model
intent is no longer only metadata: read-only requests get no proposal tools; explicit logging
can prepare drafts without metric history. A pending clarification can continue on the next
reply within 24 hours; read-only topic changes clear it. No model tool can execute Google writes.

**Two paid runs, both synthetic and with no Google writes:** the first prepared one valid food
draft, but finished in plain text instead of submitting (5 model calls, OpenAI $0.005649 and Jev
$0.000067410). Added an explicit instruction to finish log-only tasks through `submit_findings`,
without statistical investigations or numeric claims. The second prepared one draft and submitted
in 2 calls (OpenAI $0.002841150 and Jev $0.000066948). Combined estimated spend: $0.008624508.
The reproducible smoke check is `python eval/logging_smoke.py --run-paid`, never run by CI.

**Free checks:** migrated SQLite tests cover ownership, stale versions, duplicate request keys
and entry identities, concurrent confirmation, persisted unknown outcomes, consent state, invalid
fields/units/timezones, missing-detail follow-ups, topic changes/expiry, and errors without health
payloads in logs. Scripted chat produces a saved draft and chat reference without executing it. The final local checks pass 610 backend and 71 mobile tests,
all 21 Expo Doctor checks, lint/type/format checks and the web export. Migration 0006 was applied
to the local project Postgres without reading or changing health records.
Playwright on synthetic data and a fake writer clicked draft/edit/validation/confirm/two-step
undo/unknown/cancel in light/dark at desktop/mobile widths, with no browser console errors.

**Limits:** this is not an intent/extraction accuracy evaluation or proof of provider behavior.
Actual Google create/delete, asynchronous operation reconciliation, existing-provider entry
matching, nutrition sync/deduplication, workout telemetry and photo estimates remain unvalidated
or unbuilt. `FA_GOOGLE_WRITES_ENABLED` stays false. Real account test entries and cleanup need
explicit approval. Expo Doctor's unrelated SDK 57 patch mismatch was fixed separately in PR #51.

## First real Google write, and answers that read like one reply (2026-10-25)

**Tested:** the owner connected Google from the app (first real connection: 4 read scopes, a
7-day resync), asked to log a 10 kcal test snack, edited it to 14 kcal, allowed the nutrition write
scope when asked, confirmed it, saw it in the Fitbit app and read it back from Google (name, energy
and meal matched), then undid it; the delete went through. Total chat cost $0.0166.
**Showed:** the write path works end to end. It also showed four chat problems:
- The agent did not know the time: the task said "Today is" the last day of data, so "just now" got
  a question back.
- Its follow-up ("00:53, +02:00") reached the agent without the request it answered, and the model
  answered the first turn's sleep question instead.
- Answers pasted each verified claim as its own sentence ("time asleep did not clearly change…"
  four times), lower-case, and the chips all read "Evidence".
- The evidence card showed the raw p (0.016) for a time-asleep drop the answer called "not clearly
  changed": correct after correcting for the run's 6 tests (0.096), but it looked like a
  contradiction. Recomputing the four tests from the stored data reproduced every value exactly.
**Changed (PR #54):** the local time and offset go into every task; a reply to a logging question
reaches the agent with its request; the summary is the answer (2 to 4 connected sentences), claims
stay as evidence; a hedged sentence may give a borderline direction for a tested metric; "slept"
counts as time asleep; chips name their metric; the card shows units, the p-value the answer was
judged on and a plain verdict. A rerun of the sleep question ($0.0098) gave one natural paragraph.
That rerun ran 5 tests instead of 6, so the same drop came out significant (0.04) and was called a
small real dip: open issue 20. "Log a snack… just now" still asked for the time ($0.0042), because
the logging tool's own description told the model to ask; fixed, not yet rerun.
