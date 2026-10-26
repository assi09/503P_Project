"""Two paid questions about the app's own scores, on a synthetic person.

The person's still heart rate rises by a planted amount in the last two weeks, so a sound answer
about stress finds it higher, and one about strain describes it from the zone minutes.

Run explicitly from the repository root with the venv active:
    python eval/scores_smoke.py --run-paid
Prints the routing, verification and cost of each answer. Record the cost in docs/costs.md and
experiments.md.
"""

import argparse
import json
from datetime import date, timedelta

import numpy as np
from app.agent.ask import ask, default_guard, default_router
from app.agent.llm import OpenAILLM
from app.analysis.day import with_scores
from app.config import settings
from app.synthetic import generate

START = date(2026, 7, 1)
DAYS = 90
QUESTIONS = (
    "Has my stress score been higher in the last two weeks?",
    "How has my strain been in the last two weeks?",
)


def synthetic_frame():
    """Made-up days with zone minutes and still time; the still heart rate rises at the end."""
    frame = generate(START, DAYS, seed=11).frame
    rng = np.random.default_rng(11)
    moderate = rng.gamma(2, 12, DAYS)
    frame["hr_zone_light_minutes"] = rng.normal(800, 80, DAYS).round()
    frame["hr_zone_moderate_minutes"] = moderate.round()
    frame["hr_zone_vigorous_minutes"] = rng.gamma(1.5, 5, DAYS).round()
    frame["hr_zone_peak_minutes"] = rng.poisson(0.5, DAYS).astype(float)
    frame["still_minutes"] = rng.normal(420, 40, DAYS).round()
    above = 14 + 2 * np.log1p(2 * moderate) + rng.normal(0, 1.2, DAYS)
    above[-14:] += 4  # the planted rise
    frame["still_hr_above_resting"] = above.round(2)
    return with_scores(frame)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-paid", action="store_true", required=True)
    parser.parse_args()
    frame = synthetic_frame()
    llm, router, guard = (
        OpenAILLM.from_settings(settings),
        default_router(settings),
        default_guard(settings),
    )
    total = 0.0
    for question in QUESTIONS:
        reply = ask(
            llm,
            router,
            frame,
            question,
            today=START + timedelta(days=DAYS - 1),
            guard=guard,
        )
        result = reply.result
        jev = reply.route.classification.cost_usd + sum(
            step.get("cost_usd", 0) for step in result.trace if step["type"] == "guard"
        )
        cost = result.budget.cost_usd + jev
        total += cost
        cited = sorted({m for e in result.cited_evidence.values() for m in e.metrics})
        print(
            json.dumps(
                {
                    "question": question,
                    "routed_to": reply.route.expert,
                    "router": reply.route.classification.source,
                    "stop": result.stop_reason,
                    "claims_accepted": len(result.claims),
                    "claims_rejected": len(result.rejected),
                    "cited_metrics": cited,
                    "summary": result.summary,
                    "model_calls": result.budget.calls,
                    "cost_usd": round(cost, 6),
                },
                indent=2,
            )
        )
    print(f"total cost: ${total:.4f}")


if __name__ == "__main__":
    main()
