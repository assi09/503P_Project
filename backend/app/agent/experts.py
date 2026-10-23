"""The specialist experts: each owns a set of metrics and answers questions about them.

An expert runs the same investigation loop as the general agent (`run_agent`) with its own prompt,
a toolbox over the metrics it owns plus the ones it reads to explain them, and one extra rule:
**only the owner makes claims about a metric**. A claim about another expert's metric passes only
when every evidence it cites was produced by that expert, through `consult`.

`consult` (deep answers only) runs another expert on a narrower question with a smaller budget and
hands back its verified claims and their evidence, which the lead may then cite. Consulted experts
cannot consult in turn, so a question costs at most one lead run and a few short ones.
"""

import json
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from app.agent.agent import SYSTEM_PROMPT, AgentResult, ExtraTool, answer_task, run_agent
from app.agent.llm import LLM, Budget
from app.agent.present import label
from app.agent.tools import ALWAYS_VISIBLE, Toolbox, evidence_payload
from app.agent.verifier import Claim

CONSULT = "consult"
MAX_CONSULTS = 2
# Model calls a consult must leave the lead, so it can still submit and repair once.
LEAD_RESERVE_CALLS = 3


class Depth(StrEnum):
    QUICK = "quick"  # a small tool budget, no consultations
    DEEP = "deep"  # more tool calls, and other experts may be consulted


@dataclass(frozen=True)
class Expert:
    name: str
    owns: tuple[str, ...]
    reads: tuple[str, ...]  # other experts whose metrics it may use to explain its own
    focus: str  # what to look at first, added to the prompt
    notes: str = ""  # guardrails specific to these metrics


EXPERTS: dict[str, Expert] = {
    expert.name: expert
    for expert in (
        Expert(
            "sleep",
            owns=(
                "sleep_minutes",
                "time_in_bed",
                "sleep_efficiency",
                "sleep_score",
                "deep_sleep_minutes",
                "light_sleep_minutes",
                "rem_sleep_minutes",
                "awake_in_bed_minutes",
                "bedtime_hour",
            ),
            reads=("activity",),
            focus="Check bedtime and time in bed before anything else: most changes in time "
            "asleep come from going to bed later or earlier.",
        ),
        Expert(
            "recovery",
            owns=(
                "hrv_ms",
                "resting_hr",
                "respiratory_rate",
                "skin_temp_variation_c",
                "readiness",
            ),
            reads=("sleep", "activity"),
            focus="Look at the nights and training before a change: shorter sleep and hard "
            "training days often show up in HRV and resting heart rate a day or two later.",
            notes="Readiness is Fitbit's own score, kept for comparison; describe it, do not "
            "build on it.",
        ),
        Expert(
            "activity",
            owns=(
                "steps",
                "distance_km",
                "active_zone_minutes",
                "sedentary_minutes",
                "lightly_active_minutes",
                "moderately_active_minutes",
                "very_active_minutes",
                "calories",
                "cardio_load",
            ),
            reads=("recovery", "sleep"),
            focus="Check wear time first: days the device was barely worn lower every activity "
            "total. Then look for weekday and weekend patterns.",
            notes="Calories burned is a low-confidence estimate: describe only relative changes "
            '("about 15% above your usual"), never claims built on its absolute value.',
        ),
        # No nutrition columns exist yet; the expert is listed so routing can name it.
        Expert(
            "nutrition",
            owns=(),
            reads=("sleep", "activity"),
            focus="Look at energy and macronutrients before single nutrients.",
        ),
    )
}

# Shared by every expert: each must account for low-wear days, and may say so.
SHARED = ALWAYS_VISIBLE

BUDGETS = {
    Depth.QUICK: Budget(max_calls=6, max_tool_calls=8, max_cost_usd=0.02),
    Depth.DEEP: Budget(max_calls=16, max_tool_calls=24, max_cost_usd=0.06),
}
CONSULT_BUDGET = Budget(max_calls=5, max_tool_calls=6, max_cost_usd=0.015)


def owner(metric: str) -> Expert | None:
    return next((e for e in EXPERTS.values() if metric in e.owns), None)


def available(expert: Expert, frame: pd.DataFrame) -> bool:
    """An expert can answer only when at least one of its metrics has data."""
    return any(m in frame.columns and frame[m].notna().any() for m in expert.owns)


def visible_metrics(expert: Expert) -> list[str]:
    """What the expert's tools may compute on: its own metrics and the ones it reads."""
    read = [m for name in expert.reads for m in EXPERTS[name].owns]
    return [*expert.owns, *read]


def _names(metrics) -> str:
    return ", ".join(label(m) for m in metrics) or "none"


def system_prompt(expert: Expert, frame: pd.DataFrame, depth: Depth, consultable: list[str]) -> str:
    owned = [m for m in expert.owns if m in frame.columns]
    read = [m for m in visible_metrics(expert) if m in frame.columns and m not in expert.owns]
    lines = [
        SYSTEM_PROMPT,
        f"You are the {expert.name} expert.",
        f"- You make claims only about your metrics: {_names(owned)}. Every claim's metric must "
        "be one of these, or wear time when data quality matters.",
        f"- You may use these to explain changes in yours, but not make claims about them: "
        f"{_names(read)}.",
        f"- {expert.focus}",
    ]
    if expert.notes:
        lines.append(f"- {expert.notes}")
    # Without the owners' metrics the model cannot tell that "HRV" means asking recovery.
    others = [e for e in EXPERTS.values() if e.name != expert.name and available(e, frame)]
    lines.append(
        "- Other experts and the metrics they own: "
        + "; ".join(f"{e.name}: {_names(m for m in e.owns if m in frame.columns)}" for e in others)
        + "."
    )
    if depth is Depth.DEEP and consultable:
        lines.append(
            f"- When the question is about a metric you cannot see, call {CONSULT} with the "
            "expert that owns it and a short question before you answer; never describe a "
            "metric no evidence in this run covers. You may cite the evidence a consult "
            f"returns, including in claims about that expert's metrics. Consult at most "
            f"{MAX_CONSULTS} times."
        )
    else:
        lines.append(
            "- When the question is about a metric you cannot see, answer what your metrics show "
            "and say which expert to ask about the rest; never describe that metric yourself."
        )
    return "\n".join(lines)


def ownership_check(expert: Expert, borrowed: dict[str, str]):
    """The claim rule for an expert. `borrowed` maps evidence ids to the expert that made them."""

    def check(claim: Claim) -> list[str]:
        metric = claim.metric
        if metric is None:
            if claim.kind == "data_quality":
                return []
            return ["say which of your metrics the claim is about"]
        if metric in expert.owns or metric in SHARED:
            return []
        metric_owner = owner(metric)
        if metric_owner and all(borrowed.get(i) == metric_owner.name for i in claim.evidence_ids):
            return []
        whose = f"the {metric_owner.name} expert's" if metric_owner else "not one of your"
        return [
            f"{label(metric)} is {whose} metric: claim only what its owner's evidence shows, "
            "or leave it out"
        ]

    return check


class ConsultArguments(BaseModel):
    expert: str
    question: str = Field(min_length=1, max_length=300)


@dataclass
class _Consults:
    """The consult tool for one lead run: runs the other expert and lends its evidence."""

    llm: LLM
    frame: pd.DataFrame
    lead: Expert
    toolbox: Toolbox  # the lead's: consulted evidence is added so it can be cited
    budget: Budget  # the lead's: consults are charged to it
    today: date | None
    borrowed: dict[str, str]
    consulted: list[str]

    def experts(self) -> list[str]:
        return [
            name
            for name, e in EXPERTS.items()
            if name != self.lead.name and available(e, self.frame)
        ]

    def tool(self) -> ExtraTool:
        parameters = ConsultArguments.model_json_schema()
        parameters.pop("title", None)
        parameters["properties"]["expert"]["enum"] = self.experts()
        return ExtraTool(
            CONSULT,
            "Ask another expert about its metrics. Returns its verified claims and their "
            "evidence, which you may cite.",
            parameters,
            self.run,
        )

    def _refuse(self, message: str) -> tuple[str, dict]:
        return json.dumps({"error": message}), {"error": message}

    def run(self, arguments: dict | None) -> tuple[str, dict]:
        try:
            args = ConsultArguments.model_validate(arguments or {})
        except ValidationError:
            return self._refuse("Give an expert and a short question.")
        if args.expert not in self.experts():
            return self._refuse(f"Consult one of: {', '.join(self.experts())}.")
        if len(self.consulted) >= MAX_CONSULTS:
            return self._refuse(f"You have consulted {MAX_CONSULTS} times; submit now.")
        if args.expert in self.consulted:
            return self._refuse(f"You already consulted the {args.expert} expert.")
        calls_left = self.budget.max_calls - self.budget.calls - LEAD_RESERVE_CALLS
        cost_left = (self.budget.max_cost_usd - self.budget.cost_usd) / 2
        if calls_left < 2:
            return self._refuse("Not enough budget left to consult; submit with what you have.")

        child = replace(
            CONSULT_BUDGET,
            max_calls=min(CONSULT_BUDGET.max_calls, calls_left),
            max_cost_usd=min(CONSULT_BUDGET.max_cost_usd, cost_left),
        )
        result = ask_expert(
            self.llm,
            self.frame,
            args.expert,
            args.question,
            depth=Depth.QUICK,
            today=self.today,
            budget=child,
        )
        self.consulted.append(args.expert)
        self.budget.calls += child.calls
        self.budget.cost_usd += child.cost_usd

        lent = result.cited_evidence
        for evidence_id, evidence in lent.items():
            self.toolbox.evidence[evidence_id] = evidence
            self.borrowed[evidence_id] = args.expert
        content = {
            "expert": args.expert,
            "summary": result.summary,
            "claims": [claim.model_dump() for claim in result.claims],
            "evidence": [evidence_payload(e) for e in lent.values()],
        }
        if not result.claims:
            content["note"] = "The expert found nothing it could verify."
        step = {
            "expert": args.expert,
            "question": args.question,
            "run_id": result.run_id,
            "stop_reason": result.stop_reason,
            "claims": len(result.claims),
            "cost_usd": child.cost_usd,
            "steps": result.trace,
        }
        return json.dumps(content), step


def ask_expert(
    llm: LLM,
    frame: pd.DataFrame,
    name: str,
    question: str,
    *,
    depth: Depth = Depth.QUICK,
    today: date | None = None,
    budget: Budget | None = None,
) -> AgentResult:
    """Has one expert answer a question about the person's data, with verified claims."""
    expert = EXPERTS[name]
    budget = budget or replace(BUDGETS[depth])
    if not available(expert, frame):
        return AgentResult(
            run_id="",
            stop_reason="unavailable",
            expert=name,
            summary=f"There is no {name} data to look at yet.",
            budget=budget,
        )
    toolbox = Toolbox(frame, visible_metrics(expert))
    borrowed: dict[str, str] = {}
    consults = _Consults(llm, frame, expert, toolbox, budget, today, borrowed, [])
    extras = [consults.tool()] if depth is Depth.DEEP and consults.experts() else []
    prompt = system_prompt(expert, frame, depth, consults.experts() if extras else [])
    result = run_agent(
        llm,
        toolbox,
        answer_task(toolbox, question, today),
        system_prompt=prompt,
        budget=budget,
        extra_tools=extras,
        claim_check=ownership_check(expert, borrowed),
    )
    result.expert = name
    result.consulted = consults.consulted
    return result
