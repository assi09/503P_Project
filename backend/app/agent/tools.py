"""The tools the agent may call: descriptions for the model, argument checks, and dispatch to the
deterministic analysis tools.

The model only chooses a tool, metrics and dates; the computing happens here, on data the server
holds. A toolbox is built per run with the metrics its expert may see, and keeps every `Evidence`
it produced so the verifier can check claims against them. Problems with a call are returned to
the model as an error it can correct, never raised.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.llm import ToolCall
from app.agent.present import display, label
from app.analysis import tools as analysis
from app.analysis.day import compare_day
from app.analysis.evidence import Evidence, ToolError, Window

# Kept with any metric set: activity totals are not comparable on days the device was barely worn.
ALWAYS_VISIBLE = ("wear_minutes",)


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Period(_Arguments):
    start: date = Field(description="First day, YYYY-MM-DD")
    end: date = Field(description="Last day (inclusive), YYYY-MM-DD")


class MetricPeriod(Period):
    metric: str = Field(description="A metric from the list")


class CompareArguments(_Arguments):
    metric: str = Field(description="A metric from the list")
    recent_start: date
    recent_end: date
    baseline_start: date = Field(description="The baseline must not overlap the recent window")
    baseline_end: date


class DayArguments(_Arguments):
    metric: str = Field(description="A metric from the list")
    day: date = Field(description="The day, YYYY-MM-DD; the last day of data for 'today'")


class CorrelateArguments(Period):
    driver: str = Field(description="The metric that may explain the change")
    target: str = Field(description="The metric that changed")
    max_lag: int = Field(0, ge=0, le=analysis.MAX_LAG_DAYS, description="Days the effect may lag")


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    arguments: type[_Arguments]
    run: Callable[[pd.DataFrame, _Arguments], Evidence]


def _window(args: _Arguments, prefix: str = "") -> Window:
    return Window(start=getattr(args, f"{prefix}start"), end=getattr(args, f"{prefix}end"))


TOOLS: dict[str, AgentTool] = {
    tool.name: tool
    for tool in (
        AgentTool(
            "describe",
            "Summary of one metric over a period: mean, median, spread, range, missing days.",
            MetricPeriod,
            lambda frame, a: analysis.describe(frame, a.metric, _window(a)),
        ),
        AgentTool(
            "coverage",
            "How complete each metric is over a period, and which days had low wear time. "
            "Check this before trusting a change: gaps and low wear can fake one.",
            Period,
            lambda frame, a: analysis.coverage(frame, _window(a)),
        ),
        AgentTool(
            "compare_windows",
            "Whether a metric differs between a recent period and an earlier baseline "
            "(Mann-Whitney U, Cliff's delta). Use it to confirm and size a change.",
            CompareArguments,
            lambda frame, a: analysis.compare_windows(
                frame, a.metric, _window(a, "recent_"), _window(a, "baseline_")
            ),
        ),
        AgentTool(
            "trend",
            "Whether a metric drifts steadily over a period (Theil-Sen slope per day).",
            MetricPeriod,
            lambda frame, a: analysis.trend(frame, a.metric, _window(a)),
        ),
        AgentTool(
            "change_point",
            "The day a metric most likely shifted to a new level within a period, and whether "
            "the shift is real (permutation test). Use it to date a change before looking for "
            "what else changed around then.",
            MetricPeriod,
            lambda frame, a: analysis.change_point(frame, a.metric, _window(a)),
        ),
        AgentTool(
            "correlate",
            "Whether the target moves with a driver on the same day or up to max_lag days later "
            "(Spearman, adjusted for the lags tried). Shows association, not cause.",
            CorrelateArguments,
            lambda frame, a: analysis.correlate(frame, a.driver, a.target, _window(a), a.max_lag),
        ),
        AgentTool(
            "compare_day",
            "One day's value against the person's usual range (the middle half of the 28 days "
            "before): above, below or within. Use it for questions about today, last night or "
            "a single day. It describes where the day sits; it is not a test of a change.",
            DayArguments,
            lambda frame, a: compare_day(frame, a.metric, a.day),
        ),
        AgentTool(
            "weekday_split",
            "Whether a metric differs on weekends from weekdays.",
            MetricPeriod,
            lambda frame, a: analysis.weekday_split(frame, a.metric, _window(a)),
        ),
    )
}

METRIC_FIELDS = ("metric", "driver", "target")


@dataclass(frozen=True)
class ToolResult:
    content: str  # what the model reads: the evidence, or what was wrong with the call
    evidence: Evidence | None = None
    error: str | None = None


def evidence_payload(evidence: Evidence) -> dict:
    """The evidence as the model sees it: everything it may cite, keyed by id, with the values as
    a person reads them under `display` (the raw statistics are unchanged)."""
    return {
        "evidence_id": evidence.id,
        "tool": evidence.tool,
        "metrics": list(evidence.metrics),
        "labels": {metric: label(metric) for metric in evidence.metrics},
        "display": display(evidence),
        "windows": [
            {"start": w.start.isoformat(), "end": w.end.isoformat()} for w in evidence.windows
        ],
        "n": evidence.n,
        "sufficient": evidence.sufficient,
        "stats": evidence.stats,
    }


class Toolbox:
    def __init__(
        self, frame: pd.DataFrame, metrics: Iterable[str], tools: Iterable[str] | None = None
    ):
        allowed = set(metrics)
        self.metrics = tuple(sorted(c for c in frame.columns if c in allowed))
        context = [c for c in ALWAYS_VISIBLE if c in frame.columns and c not in allowed]
        self.frame = frame[[*self.metrics, *context]]
        self.tools = {name: TOOLS[name] for name in (tools or TOOLS)}
        self.evidence: dict[str, Evidence] = {}
        self.produced: list[str] = []  # ids of the evidence this run's own tool calls made
        days = frame.index
        self.first_day = days.min().date() if len(days) else None
        self.last_day = days.max().date() if len(days) else None

    def schemas(self) -> list[dict]:
        """The tools in the format the model API expects, with the allowed metrics listed."""
        schemas = []
        for tool in self.tools.values():
            parameters = tool.arguments.model_json_schema()
            for name in METRIC_FIELDS:
                if name in parameters.get("properties", {}):
                    parameters["properties"][name]["enum"] = list(self.metrics)
            parameters.pop("title", None)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )
        return schemas

    def run(self, call: ToolCall) -> ToolResult:
        if call.error:
            return self._error(call.error)
        tool = self.tools.get(call.name)
        if tool is None:
            return self._error(f"Unknown tool {call.name!r}. Available: {', '.join(self.tools)}.")
        try:
            args = tool.arguments.model_validate(call.arguments or {})
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors()
            )
            return self._error(f"Invalid arguments: {problems}.")
        for name in METRIC_FIELDS:
            metric = getattr(args, name, None)
            if metric is not None and metric not in self.metrics:
                return self._error(
                    f"Metric {metric!r} is not available here. Use one of: "
                    f"{', '.join(self.metrics)}."
                )
        dates = [value for value in args.model_dump().values() if isinstance(value, date)]
        if self.first_day and any(d < self.first_day or d > self.last_day for d in dates):
            return self._error(
                f"Dates must be between {self.first_day} and {self.last_day}, the data available."
            )
        try:
            evidence = tool.run(self.frame, args)
        except (ToolError, ValueError) as exc:
            return self._error(str(exc))
        self.evidence[evidence.id] = evidence
        self.produced.append(evidence.id)
        return ToolResult(content=json.dumps(evidence_payload(evidence)), evidence=evidence)

    @staticmethod
    def _error(message: str) -> ToolResult:
        return ToolResult(content=json.dumps({"error": message}), error=message)
