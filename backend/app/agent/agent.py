"""The investigation loop: hypotheses, tool calls, a verified submission.

The model proposes what might explain a change, tests each idea with the analysis tools, and hands
in claims that cite the evidence. The verifier checks every claim; rejected claims go back to the
model once with the reasons, and whatever still fails is dropped. The run stops on submission, when
its budget is spent, or on a model error, and always returns what it has, with a full trace.

This is the general agent (all metrics, no routing). The experts (`experts.py`) reuse `run_agent`
with their own prompt, metrics, an extra claim rule and the `consult` tool.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from app.agent.guard import REASON as ADVICE_REASON
from app.agent.guard import Guard, GuardError
from app.agent.llm import LLM, Budget, BudgetExceeded, LLMError, Role, ToolCall
from app.agent.present import column, metric_list
from app.agent.tools import Toolbox, evidence_payload
from app.agent.verifier import (
    Claim,
    Hypothesis,
    Rejection,
    Submission,
    Verdict,
    run_adjusted,
    text_problems,
    verify,
)
from app.analysis.evidence import Evidence
from app.analysis.screen import screen

SUBMIT = "submit_findings"
HYPOTHESES = "record_hypotheses"
REPAIR_ROUNDS = 1
NUDGES = 1  # times a reply without a tool call is answered with a reminder to submit


class HypothesesArguments(BaseModel):
    hypotheses: list[str] = Field(min_length=1, max_length=8)


SYSTEM_PROMPT = """You analyze one person's own Fitbit data and explain what changed and why.

How to work:
1. Read the task. Before testing anything, call record_hypotheses with the explanations worth
   checking, for example a bedtime shift, more or less training, low wear time or missing data,
   a weekday/weekend pattern, or a change in another metric that tracks this one.
2. Test each hypothesis with the analysis tools. Date a change with change_point, size it with
   compare_windows, check data quality with coverage, and look for metrics that move with it with
   correlate. Every tool returns evidence with an evidence_id.
3. Call submit_findings once, with a short summary, your claims and each hypothesis's status.

Writing for the person (the summary and every claim's text are shown to them as written):
- At most 4 claims, the ones that matter most, each one plain sentence. The summary is one or two
  sentences.
- Call metrics by the names in the task ("time asleep", "bedtime"), never by tool names such as
  sleep_minutes.
- Quote values as they appear under `display` in the evidence ("7 h 12 min", "23:30", "45 min",
  "12%"), and dates as "Aug 15".
- Never write evidence ids in the text: they go in evidence_ids only.

Rules for claims:
- Each claim cites the evidence_ids it rests on, says which metric it is about, and for a change or
  an association says whether it goes up or down.
- Quote only numbers, times and dates that appear in the cited evidence.
- Significance is judged after correcting for every test you run, so test what the question
  needs rather than everything you can.
- Only claim a change or an association when the evidence is significant. When it is not, that is
  a finding too: make it a no_change claim citing that evidence ("no clear change", "did not
  clearly go with"), never a change or association claim.
- The tools show change and association, not cause: write "went with" or "coincided with", never
  "caused", "because of" or "due to".
- Describe patterns in the person's data. Never diagnose or give medical advice, and never reason
  about calorie balance: calories burned is only an estimate.
"""


@dataclass(frozen=True)
class ExtraTool:
    """A tool the caller adds to the loop, such as `consult`. It returns what the model reads and
    the step to record in the trace."""

    name: str
    description: str
    parameters: dict
    run: Callable[[dict | None], tuple[str, dict]]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentResult:
    run_id: str
    # submitted, budget, model_error, no_submission, nothing_to_explain, unavailable
    stop_reason: str
    expert: str = "general"
    consulted: list[str] = field(default_factory=list)
    summary: str = ""
    claims: list[Claim] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    recorded_hypotheses: list[str] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    error: str | None = None

    @property
    def cited_evidence(self) -> dict[str, Evidence]:
        ids = {i for claim in self.claims for i in claim.evidence_ids}
        return {i: e for i, e in self.evidence.items() if i in ids}


def _control_tools() -> list[dict]:
    submission = Submission.model_json_schema()
    submission.pop("title", None)
    hypotheses = HypothesesArguments.model_json_schema()
    hypotheses.pop("title", None)
    return [
        {
            "type": "function",
            "function": {
                "name": HYPOTHESES,
                "description": "Record the explanations you will test, before testing them.",
                "parameters": hypotheses,
            },
        },
        {
            "type": "function",
            "function": {
                "name": SUBMIT,
                "description": "Hand in the summary, the claims with their evidence_ids, and the "
                "status of each hypothesis. Claims are verified against the evidence.",
                "parameters": submission,
            },
        },
    ]


def _rejections_message(rejected: list[Rejection], accepted: int, summary: list[str]) -> str:
    return json.dumps(
        {
            "accepted_claims": accepted,
            "rejected_claims": [
                {"text": r.claim.text, "reasons": list(r.reasons)} for r in rejected
            ],
            "summary_problems": summary,
            "instruction": "Fix or drop the rejected claims and call submit_findings again with "
            "the complete list of claims.",
        }
    )


def run_agent(
    llm: LLM,
    toolbox: Toolbox,
    task: str,
    *,
    system_prompt: str = SYSTEM_PROMPT,
    budget: Budget | None = None,
    role: Role = Role.SMALL,
    extra_tools: list[ExtraTool] = (),
    claim_check: Callable[[Claim], list[str]] | None = None,
    guard: Guard | None = None,
) -> AgentResult:
    budget = budget or Budget()
    result = AgentResult(run_id=uuid.uuid4().hex[:12], stop_reason="no_submission", budget=budget)
    result.evidence = toolbox.evidence  # shared: tools add to it as they run
    extras = {tool.name: tool for tool in extra_tools}
    tools = toolbox.schemas() + [tool.schema() for tool in extras.values()] + _control_tools()
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    repairs_left, nudges_left = REPAIR_ROUNDS, NUDGES

    while True:
        if budget.max_calls - budget.calls <= 1:
            messages.append(
                {"role": "user", "content": f"This is your last turn: call {SUBMIT} now."}
            )
        try:
            completion = llm.complete(messages, role=role, tools=tools, budget=budget)
        except BudgetExceeded as exc:
            result.stop_reason, result.error = "budget", str(exc)
            break
        except LLMError as exc:
            result.stop_reason, result.error = "model_error", str(exc)
            break
        messages.append(completion.as_message())
        result.trace.append(
            {
                "type": "llm",
                "model": completion.model,
                "latency_s": round(completion.latency_s, 3),
                "cost_usd": completion.cost_usd,
                "input_tokens": completion.usage.input_tokens,
                "output_tokens": completion.usage.output_tokens,
                "text": (completion.text or "")[:500],
                "tool_calls": [call.name for call in completion.tool_calls],
            }
        )

        if not completion.tool_calls:
            if nudges_left:
                nudges_left -= 1
                messages.append({"role": "user", "content": f"Use the tools, then call {SUBMIT}."})
                continue
            break

        submitted = False
        # The budget is charged for the whole turn at once; calls run in order until it is spent,
        # so a turn with too many calls loses only the ones past the limit.
        used = budget.tool_calls - len(completion.tool_calls)
        for call in completion.tool_calls:
            used += 1
            content, done = _handle(
                call,
                toolbox,
                result,
                used > budget.max_tool_calls,
                repairs_left,
                extras,
                claim_check,
                guard,
            )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
            # A verified submission sent back for repair uses up the repair round.
            if call.name == SUBMIT and not done and result.trace[-1]["type"] == "verify":
                repairs_left -= 1
            submitted = submitted or done
        if submitted:
            result.stop_reason = "submitted"
            break
    return result


def _handle(
    call: ToolCall,
    toolbox: Toolbox,
    result: AgentResult,
    over_budget: bool,
    repairs_left: int,
    extras: dict[str, ExtraTool],
    claim_check: Callable[[Claim], list[str]] | None,
    guard: Guard | None,
) -> tuple[str, bool]:
    """Runs one tool call; returns what the model reads and whether the run is finished."""
    if call.name == HYPOTHESES:
        try:
            args = HypothesesArguments.model_validate(call.arguments or {})
        except ValidationError:
            return json.dumps({"error": "Give 1 to 8 hypotheses as a list of strings."}), False
        result.recorded_hypotheses = args.hypotheses
        result.trace.append({"type": "hypotheses", "items": args.hypotheses})
        return json.dumps({"recorded": len(args.hypotheses)}), False

    if call.name == SUBMIT:
        try:
            submission = Submission.model_validate(call.arguments or {})
        except ValidationError as exc:
            message = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            result.trace.append({"type": "submit", "error": message})
            return json.dumps({"error": f"Invalid submission: {message}"}), False
        # Models sometimes name the metric as people do ("bedtime"); the checks need the column.
        claims = [
            c.model_copy(update={"metric": column(c.metric)}) if c.metric else c
            for c in submission.claims
        ]
        # The run's own tests are judged together; evidence from the screen, a consult or an
        # earlier answer keeps the correction of the run that made it.
        own = [toolbox.evidence[i] for i in toolbox.produced]
        toolbox.evidence.update({e.id: e for e in run_adjusted(own)})
        verdict = verify(claims, toolbox.evidence, claim_check)
        # The summary is shown too: it may only use what the run's evidence holds.
        summary_problems = text_problems(submission.summary, list(toolbox.evidence.values()))
        if guard:
            verdict, summary_problems = _guarded(
                guard, verdict, submission.summary, summary_problems, result
            )
        result.summary = submission.summary
        result.hypotheses = submission.hypotheses
        result.claims = list(verdict.accepted)
        result.rejected = list(verdict.rejected)
        result.trace.append(
            {
                "type": "verify",
                "accepted": len(verdict.accepted),
                "rejected": [
                    {"text": r.claim.text, "reasons": list(r.reasons)} for r in verdict.rejected
                ],
                "summary_problems": summary_problems,
            }
        )
        if (verdict.rejected or summary_problems) and repairs_left > 0:
            message = _rejections_message(
                list(verdict.rejected), len(verdict.accepted), summary_problems
            )
            return message, False
        if summary_problems:  # still wrong after the repair: show a verified claim instead
            result.summary = verdict.accepted[0].text if verdict.accepted else ""
        return json.dumps({"accepted_claims": len(verdict.accepted)}), True

    if over_budget:
        message = f"The tool budget is spent; call {SUBMIT} now with what you have."
        result.trace.append({"type": "tool", "name": call.name, "error": message})
        return json.dumps({"error": message}), False

    if call.name in extras:
        content, step = extras[call.name].run(call.arguments)
        result.trace.append({"type": call.name, **step})
        return content, False

    outcome = toolbox.run(call)
    step = {"type": "tool", "name": call.name, "arguments": call.arguments}
    if outcome.evidence:
        step["evidence_id"] = outcome.evidence.id
    else:
        step["error"] = outcome.error
    result.trace.append(step)
    return outcome.content, False


def _guarded(
    guard: Guard, verdict: Verdict, summary: str, summary_problems: list[str], result: AgentResult
) -> tuple[Verdict, list[str]]:
    """Puts what passed the deterministic checks to the guard; flagged sentences are rejected.

    Only sentences that would otherwise be shown are checked. When the guard is unavailable, the
    word checks alone apply and the trace says so."""
    claims = list(verdict.accepted)
    texts = [c.text for c in claims] + ([summary] if summary and not summary_problems else [])
    if not texts:
        return verdict, summary_problems
    try:
        judgement = guard.judge(texts)
    except GuardError as exc:
        result.trace.append({"type": "guard", "error": str(exc)})
        return verdict, summary_problems
    flags = judgement.flagged
    result.trace.append(
        {
            "type": "guard",
            "checked": len(texts),
            "flagged": [text for text, flag in zip(texts, flags, strict=True) if flag],
            "latency_s": round(judgement.latency_s, 3),
            "cost_usd": judgement.cost_usd,
        }
    )
    accepted = tuple(c for c, flag in zip(claims, flags, strict=False) if not flag)
    rejected = verdict.rejected + tuple(
        Rejection(c, (ADVICE_REASON,)) for c, flag in zip(claims, flags, strict=False) if flag
    )
    if len(texts) > len(claims) and flags[-1]:  # the summary was checked last
        summary_problems = [*summary_problems, ADVICE_REASON]
    return Verdict(accepted, rejected), summary_problems


def _describe_range(toolbox: Toolbox) -> str:
    return (
        f"Data covers {toolbox.first_day} to {toolbox.last_day}. "
        f"Metrics you can use, with what people call them: {metric_list(toolbox.metrics)}."
    )


def investigate(
    llm: LLM,
    frame: pd.DataFrame,
    metrics: list[str] | None = None,
    *,
    budget: Budget | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> AgentResult:
    """Screens the metrics for recent changes and has the agent explain them.

    The screen is deterministic and corrects for testing many metrics at once. When it finds no
    change, the model is not called at all.
    """
    toolbox = Toolbox(frame, metrics or list(frame.columns))
    found = screen(toolbox.frame)
    changes = [c for c in found.changes if c.metric in toolbox.metrics]
    for evidence in found.tested:
        toolbox.evidence[evidence.id] = evidence
    if not changes:
        return AgentResult(
            run_id=uuid.uuid4().hex[:12],
            stop_reason="nothing_to_explain",
            summary="No metric changed enough in the last two weeks to report.",
            evidence=toolbox.evidence,
            budget=budget or Budget(),
        )
    listed = "\n".join(f"- {c.metric}: {json.dumps(evidence_payload(c.evidence))}" for c in changes)
    task = (
        f"{_describe_range(toolbox)}\n\nThe screen compared the last two weeks with the four "
        f"weeks before ({found.recent.start} to {found.recent.end} against {found.baseline.start} "
        f"to {found.baseline.end}) and found these changes, already corrected for testing many "
        f"metrics:\n{listed}\n\nExplain what changed and what in the data went with it."
    )
    return run_agent(llm, toolbox, task, budget=budget, system_prompt=system_prompt)


def answer(
    llm: LLM,
    frame: pd.DataFrame,
    question: str,
    metrics: list[str] | None = None,
    *,
    today: date | None = None,
    budget: Budget | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    context: str = "",
    evidence: dict[str, Evidence] | None = None,
    guard: Guard | None = None,
) -> AgentResult:
    """Answers a person's question about their data, with verified claims.

    `context` is the conversation block from `context.build`, and `evidence` what it lets the run
    cite without recomputing."""
    toolbox = Toolbox(frame, metrics or list(frame.columns))
    toolbox.evidence.update(evidence or {})
    task = answer_task(toolbox, question, today, context)
    return run_agent(llm, toolbox, task, budget=budget, system_prompt=system_prompt, guard=guard)


def answer_task(
    toolbox: Toolbox, question: str, today: date | None = None, context: str = ""
) -> str:
    when = f"Today is {today}. " if today else ""
    earlier = f"\n\n{context}" if context else ""
    return f"{when}{_describe_range(toolbox)}{earlier}\n\nThe person asks: {question}"


def trace_json(result: AgentResult) -> str:
    """The run as JSON, for storing and for showing how an answer was reached."""
    return json.dumps(
        {
            "run_id": result.run_id,
            "expert": result.expert,
            "consulted": result.consulted,
            "stop_reason": result.stop_reason,
            "error": result.error,
            "cost_usd": result.budget.cost_usd,
            "model_calls": result.budget.calls,
            "tool_calls": result.budget.tool_calls,
            "hypotheses": result.recorded_hypotheses,
            "claims": [c.model_dump() for c in result.claims],
            "rejected": [
                {"claim": r.claim.model_dump(), "reasons": list(r.reasons)} for r in result.rejected
            ],
            "steps": result.trace,
        },
        default=str,
    )
