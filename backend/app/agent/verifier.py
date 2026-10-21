"""Deterministic checks on every claim the agent makes, before anyone sees it.

A claim must cite evidence that exists and had enough data. What it asserts must hold in that
evidence: a change or an association must be significant and in the stated direction, every number
in the sentence must come from the cited statistics (allowing rounding and minutes/hours), every
date must fall inside the cited windows, and the wording must not contradict the direction. Claims
must not diagnose, overstate causation, or reason about calorie balance from Fitbit's estimates.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.evidence import Evidence

ALPHA = 0.05

ClaimKind = Literal["change", "association", "no_change", "data_quality"]
Direction = Literal["up", "down"]


class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    kind: ClaimKind
    evidence_ids: list[str] = Field(min_length=1)
    metric: str | None = None  # the metric the claim is about
    direction: Direction | None = None  # for change and association claims


class Hypothesis(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    status: Literal["supported", "refuted", "inconclusive"]
    evidence_ids: list[str] = Field(default_factory=list)


class Submission(BaseModel):
    """What the agent hands in at the end of a run."""

    summary: str = Field(max_length=600)
    claims: list[Claim] = Field(max_length=8)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=12)


@dataclass(frozen=True)
class Rejection:
    claim: Claim
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    accepted: tuple[Claim, ...]
    rejected: tuple[Rejection, ...]


MEDICAL = re.compile(
    r"\b(diagnos\w*|disease|disorder|syndrome|apnea|insomnia|arrhythmia|a-?fib|atrial|infection|"
    r"depress\w*|prescri\w*|medication|dosage|treatment)\b",
    re.IGNORECASE,
)
CAUSAL = re.compile(
    r"\b(caused|causes|causing|because of|due to|led to|leads to|results? in|proves?)\b",
    re.IGNORECASE,
)
ENERGY_BALANCE = re.compile(
    r"\b(calorie (?:deficit|surplus|balance)|caloric (?:deficit|surplus)|net calories|"
    r"energy (?:balance|deficit|surplus)|burn(?:ed|t)? more than you (?:eat|ate))\b",
    re.IGNORECASE,
)
DOWN_WORDS = re.compile(
    r"\b(drop\w*|fell|fall\w*|decreas\w*|declin\w*|lower\w*|reduc\w*|shorter|less|fewer|down)\b",
    re.IGNORECASE,
)
UP_WORDS = re.compile(
    r"\b(ris(?:e|en|ing)|rose|increas\w*|higher|grew|grow\w*|longer|more|climb\w*|up)\b",
    re.IGNORECASE,
)

ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
MONTH_DAY = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.? (\d{1,2})\b", re.I
)
DAY_MONTH = re.compile(
    r"\b(\d{1,2}) (" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b", re.I
)
CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")


def _significant(evidence: Evidence) -> bool:
    p = evidence.stats.get("p_value_adjusted", evidence.stats.get("p_value"))
    return p is not None and p < ALPHA


def _sign(evidence: Evidence) -> float | None:
    """Which way the evidence points: positive is up, or a positive association."""
    for key in ("difference", "slope_per_day", "rho"):
        value = evidence.stats.get(key)
        if value is not None:
            return value
    return None


def _numbers_in(value) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers_in(v)]
    if isinstance(value, list | tuple):
        return [n for v in value for n in _numbers_in(v)]
    return []


# Statistics expressed in the metric's own unit, which may be quoted in a related unit.
VALUE_KEYS = (
    "mean",
    "median",
    "sd",
    "min",
    "max",
    "difference",
    "mean_recent",
    "mean_baseline",
    "mean_before",
    "mean_after",
    "mean_weekend",
    "mean_weekday",
    "slope_per_day",
    "slope_low",
    "slope_high",
    "change_over_window",
)


def _conversions(metric: str) -> tuple[float, ...]:
    """Factors from a metric's unit to the units a sentence may use for it."""
    if metric.endswith("_minutes") or metric == "time_in_bed":
        return (1, 1 / 60)  # minutes, hours
    if metric.endswith("_hour"):
        return (1, 60)  # hours, minutes
    return (1,)


def _allowed_numbers(cited: list[Evidence]) -> list[float]:
    """Every number a sentence may quote from the cited evidence, in the units people use."""
    allowed: list[float] = []
    for evidence in cited:
        factors = {f for metric in evidence.metrics for f in _conversions(metric)}
        for key, value in evidence.stats.items():
            numbers = [abs(n) for n in _numbers_in(value)]
            if key in VALUE_KEYS:
                allowed += [n * f for n in numbers for f in factors]
            elif key == "fraction_present":
                allowed += [n * 100 for n in numbers] + numbers  # shares as percentages
            else:
                allowed += numbers
        allowed.append(float(evidence.n))
        for window in evidence.windows:
            allowed += [float(window.days), window.days / 7]
    return allowed


def _quoted_numbers(text: str) -> list[tuple[float, int]]:
    """Numbers in a sentence with their decimal places, ignoring dates and clock times."""
    text = ISO_DATE.sub(" ", text)
    text = MONTH_DAY.sub(" ", text)
    text = DAY_MONTH.sub(" ", text)
    text = CLOCK.sub(" ", text)
    found = []
    for match in NUMBER.finditer(text):
        raw = match.group().replace(",", "")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        found.append((abs(float(raw)), decimals))
    return found


def _matches(number: float, decimals: int, allowed: list[float]) -> bool:
    for value in allowed:
        tolerance = max(0.5 * 10**-decimals, 0.025 * abs(value))
        if abs(number - value) <= tolerance + 1e-9:
            return True
    return False


def _quoted_dates(text: str, years: set[int]) -> list[date]:
    dates = []
    for y, m, d in ISO_DATE.findall(text):
        dates.append(date(int(y), int(m), int(d)))
    pairs = [(MONTHS[m.lower()], int(d)) for m, d in MONTH_DAY.findall(text)]
    pairs += [(MONTHS[m.lower()], int(d)) for d, m in DAY_MONTH.findall(text)]
    for month, day in pairs:
        for year in years:
            try:
                dates.append(date(year, month, day))
            except ValueError:
                continue
    return dates


def _date_supported(day: date, cited: list[Evidence]) -> bool:
    for evidence in cited:
        if evidence.stats.get("change_date") == day.isoformat():
            return True
        if any(w.start <= day <= w.end for w in evidence.windows):
            return True
    return False


def check_claim(claim: Claim, evidence: dict[str, Evidence]) -> list[str]:
    """Why the claim cannot be shown; empty when it passes."""
    missing = [i for i in claim.evidence_ids if i not in evidence]
    if missing:
        return [f"cites evidence that does not exist: {', '.join(missing)}"]
    cited = [evidence[i] for i in claim.evidence_ids]
    reasons = []

    if insufficient := [e.id for e in cited if not e.sufficient]:
        reasons.append(f"cites evidence with too little data: {', '.join(insufficient)}")
    about = [e for e in cited if claim.metric in e.metrics] if claim.metric else cited
    if claim.metric and not about:
        reasons.append(f"none of the cited evidence is about {claim.metric}")

    if claim.kind in ("change", "association"):
        tools = (
            ("correlate",)
            if claim.kind == "association"
            else (
                "compare_windows",
                "change_point",
                "trend",
                "weekday_split",
            )
        )
        support = [e for e in about if e.tool in tools and _significant(e)]
        if not support:
            reasons.append(f"no cited {claim.kind} evidence is significant at {ALPHA}")
        elif claim.direction is None:
            reasons.append("a change or association claim must state its direction")
        else:
            signs = {(_sign(e) or 0) > 0 for e in support}
            if signs != {claim.direction == "up"}:
                reasons.append(f"the evidence does not point {claim.direction}")
    if claim.kind == "no_change" and any(_significant(e) for e in about if e.tool != "coverage"):
        reasons.append("claims no change, but the cited evidence shows a significant one")
    if claim.kind == "data_quality" and not any(e.tool == "coverage" for e in cited):
        reasons.append("a data-quality claim must cite coverage evidence")

    if claim.direction and claim.kind == "change":
        up, down = bool(UP_WORDS.search(claim.text)), bool(DOWN_WORDS.search(claim.text))
        if (
            claim.direction == "up"
            and down
            and not up
            or claim.direction == "down"
            and up
            and not down
        ):
            reasons.append("the wording contradicts the stated direction")

    allowed = _allowed_numbers(cited)
    unsupported = [n for n, d in _quoted_numbers(claim.text) if not _matches(n, d, allowed)]
    if unsupported:
        reasons.append(
            "quotes numbers not found in the cited evidence: "
            + ", ".join(f"{n:g}" for n in unsupported)
        )
    years = {w.start.year for e in cited for w in e.windows} | {
        w.end.year for e in cited for w in e.windows
    }
    if bad := [d for d in _quoted_dates(claim.text, years) if not _date_supported(d, cited)]:
        reasons.append("mentions dates outside the cited evidence: " + ", ".join(map(str, bad)))

    if MEDICAL.search(claim.text):
        reasons.append("uses medical language; describe patterns, do not diagnose")
    if CAUSAL.search(claim.text):
        reasons.append("states causation; the tools show change and association, not cause")
    if ENERGY_BALANCE.search(claim.text):
        reasons.append("reasons about calorie balance, which Fitbit's estimates cannot support")
    return reasons


def verify(claims: list[Claim], evidence: dict[str, Evidence]) -> Verdict:
    accepted, rejected = [], []
    for claim in claims:
        reasons = check_claim(claim, evidence)
        if reasons:
            rejected.append(Rejection(claim, tuple(reasons)))
        else:
            accepted.append(claim)
    return Verdict(tuple(accepted), tuple(rejected))
