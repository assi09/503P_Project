"""Answering one question from the Ask screen: build its context, route it, then refuse or answer.

The context (earlier turns, their evidence, an attachment) is chosen by code before any model runs
(`context.py`). The router sees the question and the earlier questions only. An attachment's metric
decides the lead, like picking an expert, unless the person picked one; the scope check and the
choice of consults stay with the router. A question about the conversation itself is answered from
the conversation (`conversation.py`). What the context included and how the question was routed
are the first steps of the trace, so every answer can be traced to its context and its routing.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import pandas as pd

from app.agent.agent import SYSTEM_PROMPT, AgentResult, ExtraTool, answer
from app.agent.context import Attachment, Context, MemoryItem, Turn, build, earlier_questions
from app.agent.conversation import ask_what_they_want, recall
from app.agent.experts import (
    BUDGETS,
    EXPERTS,
    LOGGING_PROMPT,
    Depth,
    ask_expert,
    available,
    owner,
    visible_metrics,
)
from app.agent.facts import FACT_KINDS, FactRejected, validate_fact
from app.agent.guard import Guard, JevGuard
from app.agent.intent import Intent
from app.agent.jev import JevClient, JevError
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
from app.analysis.evidence import Evidence

# Shown without calling the model: the refusal costs nothing and cannot be talked around.
REFUSAL = (
    "I can only describe patterns in your own Fitbit data, so I can't help with medical "
    "questions, diagnoses or advice, or with questions about anything else."
)


@dataclass
class Answer:
    route: Route
    result: AgentResult
    context: Context
    proposed_facts: list[dict] = field(default_factory=list)  # for the person to approve


PROPOSE_FACT = "propose_fact"
MAX_PROPOSALS = 1


def _propose_tool(proposals: list[dict]) -> ExtraTool:
    """Collects at most one fact for the person to approve; nothing is stored by the agent."""

    def run(arguments: dict | None) -> tuple[str, dict]:
        arguments = arguments or {}
        if len(proposals) >= MAX_PROPOSALS:
            message = "You already proposed a fact in this answer."
            return json.dumps({"error": message}), {"error": message}
        try:
            text, metrics = validate_fact(
                str(arguments.get("kind", "")),
                str(arguments.get("text", "")),
                [str(m) for m in arguments.get("metrics") or []],
            )
        except FactRejected as exc:
            return json.dumps({"error": str(exc)}), {"error": str(exc)}
        proposals.append({"kind": arguments["kind"], "text": text, "metrics": metrics})
        return (
            json.dumps({"proposed": True, "note": "The person will be asked to approve it."}),
            {"proposed": proposals[-1]},
        )

    return ExtraTool(
        PROPOSE_FACT,
        "Propose remembering something lasting the person told you about themselves in this "
        "conversation (a routine, goal, preference or context, such as 'night shifts since "
        "September'). Never something you inferred from the data. At most one per answer, at "
        "most 120 characters; it is kept only if the person approves.",
        {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(FACT_KINDS)},
                "text": {"type": "string", "maxLength": 120},
                "metrics": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["kind", "text"],
        },
        run,
    )


def _scope(route: Route) -> set[str] | None:
    """The metrics in play: the lead's own and the ones it reads, and its consults' (None: all)."""
    if route.action != "expert":
        return None
    metrics = set(visible_metrics(EXPERTS[route.expert]))
    for name in route.consult:
        metrics |= set(EXPERTS[name].owns)
    return metrics


def default_router(settings) -> Router:
    """Jev with the keyword rule as fallback; the keyword rule alone without a TypeSafe key."""
    try:
        return FallbackRouter(JevRouter.from_settings(settings), KeywordRouter())
    except RouterError:
        return KeywordRouter()


def default_guard(settings) -> Guard | None:
    """Jev checking shown text for advice; none without a TypeSafe key (word checks only)."""
    try:
        return JevGuard(JevClient.from_settings(settings))
    except JevError:
        return None


def _route_step(route: Route) -> dict:
    c = route.classification
    return {
        "type": "route",
        "source": c.source,
        "probabilities": {label: round(p, 4) for label, p in c.probabilities.items()},
        "needs": {expert: round(p, 4) for expert, p in c.needs.items()},
        "intent": c.intent,
        "intent_probabilities": {
            intent: round(p, 4) for intent, p in c.intent_probabilities.items()
        },
        "action": route.action,
        "expert": route.expert,
        "consult": list(route.consult),
        "routed": route.routed,
        "latency_s": round(c.latency_s, 3),
        "cost_usd": c.cost_usd,
        "error": c.error,
    }


def _notes(frame: pd.DataFrame, route: Route, result: AgentResult) -> list[str]:
    """Fixed sentences for what the answer could not cover, so a gap is said, not hidden."""
    missing = [
        name for name in route.consult if name in EXPERTS and not available(EXPERTS[name], frame)
    ]
    notes = [f"There is no {name} data yet, so it is left out here." for name in missing]
    if result.uncovered:
        names = " or ".join(result.uncovered)
        notes.append(
            f"Your {names} data was not checked for this answer; ask about it if you would "
            "like it looked at."
        )
    return notes


def _context_step(context: Context) -> dict:
    return {"type": "context", **context.included, "dropped": context.dropped}


def ask(
    llm: LLM,
    router: Router,
    frame: pd.DataFrame,
    question: str,
    *,
    choice: str = "auto",
    depth: Depth = Depth.QUICK,
    today: date | None = None,
    history: Sequence[Turn] = (),
    stored_evidence: dict[str, Evidence] | None = None,
    attachment: Attachment | None = None,
    guard: Guard | None = None,
    memory: Sequence[MemoryItem] = (),
    now: datetime | None = None,
    action_tools: dict[str, list[ExtraTool]] | None = None,
    continuing_log: str | None = None,
) -> Answer:
    """Routes the question and has the right agent answer it, with verified claims.

    `history` is the conversation so far (oldest first), `stored_evidence` the evidence its
    answers cite and `memory` the person's stored memory, all loaded by the caller for this person
    only. Routing comes first, so memory is chosen for the metrics the question is about."""
    if choice == "auto" and attachment and (attached := owner(attachment.metric)):
        choice = attached.name  # the attachment decides the topic
    route = decide(router.classify(question, earlier_questions(history)), choice)
    continuing = (
        (continuing_log in (action_tools or {}) or continuing_log == "general")
        and (
            choice in ("auto", continuing_log)
            or (continuing_log == "general" and choice in (action_tools or {}))
        )
        and route.classification.intent == Intent.CLARIFY
        and route.action not in ("refuse", "conversation")
    )
    if continuing:
        # This state comes from the server's unfinished clarification, not earlier text alone.
        if continuing_log == "general":
            if route.expert not in (action_tools or {}):
                route = Route("general", None, (), True, route.classification)
        else:
            route = Route("expert", continuing_log, (), choice == "auto", route.classification)
    context = build(
        history,
        stored_evidence or {},
        attachment,
        memory=memory,
        scope=_scope(route),
        now=now,
    )
    proposals: list[dict] = []
    tools = [_propose_tool(proposals)]
    logging_tools = []
    if (
        route.classification.intent in (Intent.LOG, Intent.MIXED) or continuing
    ) and route.action != "refuse":
        if route.action == "general":
            logging_tools = [tool for group in (action_tools or {}).values() for tool in group]
        else:
            # The lead's own, and in a new request those of the experts the router says it also
            # needs: "a swim after three figs" is a workout and a meal. A reply continuing a
            # request stays with its kind; its text quotes the question, which names both.
            names = (route.expert,) if continuing else (route.expert, *route.consult)
            logging_tools = [tool for name in names for tool in (action_tools or {}).get(name, [])]
    tools += logging_tools
    if route.action == "refuse":
        result = AgentResult(run_id=uuid.uuid4().hex[:12], stop_reason="refused", summary=REFUSAL)
    elif route.action == "conversation":
        result = recall(llm, question, history, guard=guard)
    elif action_tools and route.classification.intent == Intent.MANAGE:
        result = AgentResult(
            run_id=uuid.uuid4().hex[:12],
            stop_reason="action_controls",
            summary="Use the entry card to edit or cancel a draft. To remove a logged entry, "
            "choose Undo and confirm the removal. Chat messages cannot confirm Google writes.",
        )
    elif (
        action_tools
        and route.classification.intent_probabilities
        and route.classification.intent == Intent.CLARIFY
        and route.expert in ("nutrition", "activity")
        and not continuing
    ):
        result = ask_what_they_want(llm, question, expert=route.expert, guard=guard)
    elif route.action == "general":
        result = answer(
            llm,
            frame,
            question,
            today=today,
            budget=replace(BUDGETS[depth]),
            system_prompt=SYSTEM_PROMPT + (LOGGING_PROMPT if logging_tools else ""),
            context=context.block,
            evidence=context.evidence,
            guard=guard,
            extra_tools=tools,
        )
    else:
        result = ask_expert(
            llm,
            frame,
            route.expert,
            question,
            depth=depth,
            consult=route.consult,
            today=today,
            context=context.block,
            evidence=context.evidence,
            owners=context.owners,
            guard=guard,
            # A request only to log asks nothing about the data, so no part of it can be left
            # uncovered; a mixed request still needs its question answered.
            needs=()
            if logging_tools and (route.classification.intent == Intent.LOG or continuing)
            else (route.expert, *route.consult),
            extra_tools=tools,
            allow_logging=bool(logging_tools),
        )
        result.notes += _notes(frame, route, result)
    result.trace[:0] = [_context_step(context), _route_step(route)]
    if continuing:
        result.trace[1]["continuing_log_expert"] = continuing_log
    return Answer(route, result, context, proposals)
