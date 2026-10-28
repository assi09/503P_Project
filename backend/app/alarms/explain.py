"""The agent's explanation of a smart alarm, checked like any answer, with the template as fallback.

A detector decided the alarm; the expert that owns its metric now looks at what went with it (the
bedtime before a short night, training before a rise in resting heart rate) in one quick run, with
the alarm's evidence given so it can cite it. Its summary passed the verifier (every number from
evidence, no causes, no overstatement) and the advice guard inside that run; a reply that did not,
or a run that failed, leaves the template. Data alarms (no new data, reconnect) need no
explanation. Each run's cost is kept on the alarm.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from app.agent.experts import Depth, ask_expert, available, owner
from app.agent.guard import Guard
from app.agent.llm import LLM, LLMError
from app.agent.verifier import MEDICAL
from app.analysis.evidence import Evidence

logger = logging.getLogger(__name__)

MAX_BODY = 600
QUESTION = (
    "Patterns raised this alert from the person's data: {title}. {body} "
    "In two or three short sentences, say what the data shows around it, for example the bedtime "
    "or training before it, or how long it has been going on, citing evidence. Lead with the "
    "alert itself. Describe; never advise, diagnose or say what caused it."
)


@dataclass(frozen=True)
class Explanation:
    body: str
    written_by: str  # the expert, or "template"
    cost_usd: float


def explain(
    llm: LLM | None,
    frame: pd.DataFrame,
    *,
    kind: str,
    metric: str | None,
    title: str,
    body: str,
    evidence: list[Evidence],
    today,
    guard: Guard | None = None,
) -> Explanation:
    """The expert's explanation when it passes; the template body otherwise."""
    fallback = Explanation(body, "template", 0.0)
    expert = owner(metric) if metric else None
    if llm is None or kind == "data" or expert is None or not available(expert, frame):
        return fallback
    try:
        result = ask_expert(
            llm,
            frame,
            expert.name,
            QUESTION.format(title=title, body=body),
            depth=Depth.QUICK,
            today=today,
            evidence={e.id: e for e in evidence},
            owners={e.id: expert.name for e in evidence},
            guard=guard,
        )
    except LLMError as error:
        logger.warning("Explaining an alarm failed: %s", error)
        return fallback
    cost = result.budget.cost_usd
    text = result.summary.strip()
    checks = [step for step in result.trace if step.get("type") == "verify"]
    # A summary that failed its last check was replaced by the joined claims: the template reads
    # better than that.
    rejected = bool(checks and checks[-1].get("summary_problems"))
    if result.stop_reason != "submitted" or not text or rejected or MEDICAL.search(text):
        return Explanation(body, "template", cost)
    if len(text) > MAX_BODY:
        return Explanation(body, "template", cost)
    return Explanation(text, expert.name, cost)
