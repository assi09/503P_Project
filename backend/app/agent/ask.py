"""Answering one question from the Ask screen: route it, then refuse, or answer it.

The router's decision is recorded as the first step of the run's trace, with the probabilities,
which router produced them and why an earlier one failed, so every answer can be traced back to how
it was routed.
"""

import uuid
from dataclasses import dataclass, replace
from datetime import date

import pandas as pd

from app.agent.agent import AgentResult, answer
from app.agent.experts import BUDGETS, Depth, ask_expert
from app.agent.llm import LLM
from app.agent.router import (
    FallbackRouter,
    JevRouter,
    KeywordRouter,
    Route,
    Router,
    RouterError,
    decide,
)

# Shown without calling the model: the refusal costs nothing and cannot be talked around.
REFUSAL = (
    "I can only describe patterns in your own Fitbit data, so I can't help with medical "
    "questions, diagnoses or advice, or with questions about anything else."
)


@dataclass
class Answer:
    route: Route
    result: AgentResult


def default_router(settings) -> Router:
    """Jev with the keyword rule as fallback; the keyword rule alone without a TypeSafe key."""
    try:
        return FallbackRouter(JevRouter.from_settings(settings), KeywordRouter())
    except RouterError:
        return KeywordRouter()


def _route_step(route: Route) -> dict:
    c = route.classification
    return {
        "type": "route",
        "source": c.source,
        "probabilities": {label: round(p, 4) for label, p in c.probabilities.items()},
        "action": route.action,
        "expert": route.expert,
        "consult": list(route.consult),
        "routed": route.routed,
        "latency_s": round(c.latency_s, 3),
        "cost_usd": c.cost_usd,
        "error": c.error,
    }


def ask(
    llm: LLM,
    router: Router,
    frame: pd.DataFrame,
    question: str,
    *,
    choice: str = "auto",
    depth: Depth = Depth.QUICK,
    today: date | None = None,
) -> Answer:
    """Routes the question and has the right agent answer it, with verified claims."""
    route = decide(router.classify(question), choice)
    if route.action == "refuse":
        result = AgentResult(run_id=uuid.uuid4().hex[:12], stop_reason="refused", summary=REFUSAL)
    elif route.action == "general":
        result = answer(llm, frame, question, today=today, budget=replace(BUDGETS[depth]))
    else:
        result = ask_expert(
            llm, frame, route.expert, question, depth=depth, consult=route.consult, today=today
        )
    result.trace.insert(0, _route_step(route))
    return Answer(route, result)
