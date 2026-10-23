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
