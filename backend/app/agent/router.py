"""Routing a question to the expert that owns its topic.

A classifier answers two things about a question. Its **topic**: one probability per label (an
expert, `general` or `out_of_scope`) that picks the lead and checks the scope. And, independently
for each expert, whether answering **needs** that expert's data: a cross-domain question ("did my
late nights hurt my recovery?") needs two. A single topic distribution cannot say that, because its
spare probability is uncertainty, not a second topic. Code, not the classifier, decides what to do
(`decide`): refuse, hand the question to the general agent, or give it to the lead expert, which may
consult the other experts the question needs.

Jev (TypeSafe's typed decision model) is the classifier in the app. If it fails or times out, a
keyword rule over metric names routes instead, so a question is never lost to the router. An LLM
router exists for the evaluation, to compare accuracy, latency and cost. Every router receives the
question text only, never the person's data or memory: the current question and up to three earlier
ones from the conversation, so a follow-up ("and last week?") can be read in light of what it refers
to, even several questions back.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

import httpx2

from app.agent.experts import EXPERTS
from app.agent.jev import JevClient, JevError, clean
from app.agent.llm import LLM, Budget, LLMError
from app.agent.verifier import MEDICAL

GENERAL = "general"
OUT_OF_SCOPE = "out_of_scope"
EXPERT_LABELS = tuple(EXPERTS)
LABELS = (*EXPERT_LABELS, GENERAL, OUT_OF_SCOPE)

# What each label means, for the classifiers. Experts are described by the metrics they own.
CRITERIA = {
    "sleep": "time asleep, time in bed, bedtime, sleep efficiency, sleep stages (deep, light, "
    "REM), time awake at night, sleep score",
    "recovery": "recovery, heart rate variability (HRV), resting heart rate, breathing rate, "
    "skin temperature, readiness",
    "activity": "steps, distance, exercise and training, Active Zone Minutes, active and "
    "sedentary time, calories burned, cardio load",
    "nutrition": "food and drink logged: calories eaten, protein, carbohydrates, fat, nutrients, "
    "meals",
    GENERAL: "the person's own Fitbit data overall, or several areas with no main one",
    OUT_OF_SCOPE: "medical diagnosis, symptoms, treatment, medication or health advice, or "
    "anything that is not about the person's own Fitbit data",
}
INSTRUCTIONS = (
    "A person asks a question about their own Fitbit data, possibly following up on their earlier "
    "questions. Which topic is the current question about? Earlier questions, newest first, only "
    "show what it may refer to."
)


def needs_instructions(expert: str) -> str:
    return (
        f"A person asks a question about their own Fitbit data, possibly following up on their "
        f"earlier questions. Does answering the current question need their {expert} data "
        f"({CRITERIA[expert]})?"
    )


MAX_EARLIER = 3  # earlier questions the router sees, newest first

# Thresholds on the probabilities. Tuned by the router evaluation, not fitted to anyone's data.
REFUSE_AT = 0.5  # out of scope at least this likely: refuse
LEAD_AT = 0.4  # the most likely expert must reach this, or the general agent answers
CONSULT_AT = 0.5  # other experts whose data the question needs this likely are consulted


class RouterError(RuntimeError):
    """A classifier could not label the question; the message is safe to show and to log."""


@dataclass(frozen=True)
class Classification:
    probabilities: dict[str, float]  # the topic: every label, summing to 1
    needs: dict[str, float]  # per expert, the probability that answering needs its data
    source: str  # jev, keyword, llm
    latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None  # why an earlier router in the chain failed

    @property
    def top(self) -> str:
        return max(LABELS, key=lambda label: self.probabilities[label])


class Router(Protocol):
    def classify(self, question: str, earlier: Sequence[str] = ()) -> Classification: ...


def state(question: str, earlier: Sequence[str] = ()) -> dict:
    """What a router is given: the cleaned question and the latest earlier ones, newest first."""
    recent = [clean(q) for q in earlier[:MAX_EARLIER] if clean(q)]
    return {"question": clean(question), "earlier_questions": recent}


def normalized(raw: dict) -> dict[str, float]:
    """Probabilities over every label, summing to 1. Raises `RouterError` on unusable values."""
    if not isinstance(raw, dict):
        raise RouterError("The router returned no probabilities.")
    values = {label: _probability(raw.get(label, 0.0), label) for label in LABELS}
    total = sum(values.values())
    if total <= 0:
        raise RouterError("The router returned no probabilities.")
    return {label: value / total for label, value in values.items()}


def _probability(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
        raise RouterError(f"The router returned an invalid probability for {name}.")
    return float(value)


def needs_from(raw) -> dict[str, float]:
    """One independent probability per expert. Raises `RouterError` on unusable values."""
    if not isinstance(raw, dict) or set(raw) != set(EXPERT_LABELS):
        raise RouterError("The router did not say which experts' data the question needs.")
    return {expert: _probability(raw[expert], f"needs {expert}") for expert in EXPERT_LABELS}


class JevRouter:
    """Routes with Jev: no retries, since a slow or failing call falls back to the keyword rule."""

    def __init__(self, api_key: str, http: httpx2.Client | None = None, **options):
        try:
            self.client = JevClient(api_key, http, **options)
        except JevError as exc:
            raise RouterError(str(exc)) from exc
        self.model = self.client.model

    @classmethod
    def from_settings(cls, settings) -> "JevRouter":
        key = settings.typesafe_api_key
        return cls(
            key.get_secret_value() if key else "",
            model=settings.typesafe_model,
            base_url=settings.typesafe_base_url,
        )

    def payload(self, question: str, earlier: Sequence[str] = ()) -> dict:
        given = state(question, earlier)
        return {
            # A bare question when there is nothing earlier, as Jev reads plain text best.
            "state": given if given["earlier_questions"] else given["question"],
            "model": self.model,
            # Evaluated in parallel in one call: the topic, and per expert whether it is needed.
            "questions": {
                "topic": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA},
                **{
                    f"needs_{expert}": {"type": "noul", "instructions": needs_instructions(expert)}
                    for expert in EXPERT_LABELS
                },
            },
        }

    def classify(self, question: str, earlier: Sequence[str] = ()) -> Classification:
        try:
            body, latency, cost = self.client.call(self.payload(question, earlier))
        except JevError as exc:
            raise RouterError(str(exc)) from exc
        try:
            answers = body["answers"]
            topic = answers["topic"]
            needs = {e: answers[f"needs_{e}"] for e in EXPERT_LABELS}
        except (ValueError, KeyError, TypeError) as exc:
            raise RouterError("Jev's answer was not in the expected format.") from exc
        if not isinstance(topic, dict) or topic.get("type") != "choice":
            raise RouterError("Jev's answer was not in the expected format.")
        if not all(isinstance(a, dict) and a.get("type") == "noul" for a in needs.values()):
            raise RouterError("Jev's answer was not in the expected format.")
        probabilities = normalized(topic.get("probabilities"))
        needed = needs_from({e: a.get("noul") for e, a in needs.items()})
        return Classification(probabilities, needed, source="jev", latency_s=latency, cost_usd=cost)


def _words(*patterns: str) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(patterns) + r")", re.IGNORECASE)


# Patterns match at the start of a word, so "train" also matches "training".
KEYWORDS = {
    "sleep": _words(
        r"sleep",
        r"slept",
        r"bed",
        r"nap",
        r"rem\b",
        r"deep sleep",
        r"awake",
        r"wak(e|ing) up",
        r"night",
    ),
    "recovery": _words(
        r"recover",
        r"hrv",
        r"heart rate variability",
        r"resting heart",
        r"rhr\b",
        r"readiness",
        r"breathing",
        r"respirat",
        r"skin temp",
        r"temperature",
    ),
    "activity": _words(
        r"step",
        r"walk",
        r"run",
        r"exercis",
        r"workout",
        r"train",
        r"active",
        r"activity",
        r"distance",
        r"zone minutes",
        r"azm\b",
        r"sedentary",
        r"cardio",
        r"burn",
    ),
    "nutrition": _words(
        r"eat",
        r"ate\b",
        r"food",
        r"diet",
        r"protein",
        r"carb",
        r"fat\b",
        r"meal",
        r"nutri",
        r"sugar",
        r"fib(er|re)",
        r"calories (eaten|in)\b",
        r"intake",
    ),
}
# Not "sick" or "ill": "did my HRV drop when I was sick?" is a question about the data. Not
# "supplement" either: "did my protein-supplement days go with better recovery?" is one too.
OFF_TOPIC = _words(
    r"doctor",
    r"symptom",
    r"cure",
    r"medicine",
    r"melatonin",
    r"pills?\b",
    r"drugs?\b",
)


class KeywordRouter:
    """Metric words decide the topic; medical words mean out of scope. Free and instant.

    A question with no metric words takes its topic from the latest earlier question that has some.
    """

    def classify(self, question: str, earlier: Sequence[str] = ()) -> Classification:
        given = state(question, earlier)
        text = given["question"]
        probabilities = dict.fromkeys(LABELS, 0.0)
        hits = self._hits(text)
        for previous in given["earlier_questions"]:
            if any(hits.values()):
                break
            hits = self._hits(previous)
        needs = {label: 1.0 if count else 0.0 for label, count in hits.items()}
        if MEDICAL.search(text) or OFF_TOPIC.search(text):
            probabilities[OUT_OF_SCOPE] = 1.0
            return Classification(probabilities, needs, source="keyword")
        total = sum(hits.values())
        if not total:
            probabilities[GENERAL] = 1.0
        else:
            probabilities |= {label: count / total for label, count in hits.items()}
        return Classification(probabilities, needs, source="keyword")

    @staticmethod
    def _hits(text: str) -> dict[str, int]:
        return {label: len(pattern.findall(text)) for label, pattern in KEYWORDS.items()}


ROUTE_TOOL = "route"
LLM_ROUTER_PROMPT = (
    INSTRUCTIONS
    + " With the route tool, give the probability of each topic (they should sum to 1), and "
    "separately for each of sleep, recovery, activity and nutrition the probability that "
    "answering needs that data (each from 0 to 1).\n"
    + "\n".join(f"- {label}: {meaning}" for label, meaning in CRITERIA.items())
)


def _probabilities_schema(labels: tuple[str, ...]) -> dict:
    return {
        "type": "object",
        "properties": {label: {"type": "number", "minimum": 0, "maximum": 1} for label in labels},
        "required": list(labels),
    }


class LLMRouter:
    """The same labels from the language model, for comparison in the evaluation."""

    def __init__(self, llm: LLM):
        self._llm = llm

    def classify(self, question: str, earlier: Sequence[str] = ()) -> Classification:
        tool = {
            "type": "function",
            "function": {
                "name": ROUTE_TOOL,
                "description": "The probability of each topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": _probabilities_schema(LABELS),
                        "needs": _probabilities_schema(EXPERT_LABELS),
                    },
                    "required": ["topic", "needs"],
                },
            },
        }
        messages = [
            {"role": "system", "content": LLM_ROUTER_PROMPT},
            {"role": "user", "content": json.dumps(state(question, earlier))},
        ]
        budget = Budget(max_calls=1, max_tool_calls=1, max_cost_usd=0.002)
        try:
            completion = self._llm.complete(messages, tools=[tool], budget=budget)
        except LLMError as exc:
            raise RouterError(str(exc)) from exc
        call = next((c for c in completion.tool_calls if c.name == ROUTE_TOOL), None)
        if call is None or call.arguments is None:
            raise RouterError("The model did not route the question.")
        return Classification(
            normalized(call.arguments.get("topic")),
            needs_from(call.arguments.get("needs")),
            source="llm",
            latency_s=completion.latency_s,
            cost_usd=completion.cost_usd,
        )


@dataclass(frozen=True)
class FallbackRouter:
    """Tries the primary router; when it fails, the fallback answers and the reason is kept."""

    primary: Router
    fallback: Router

    def classify(self, question: str, earlier: Sequence[str] = ()) -> Classification:
        try:
            return self.primary.classify(question, earlier)
        except RouterError as exc:
            return replace(self.fallback.classify(question, earlier), error=str(exc))


@dataclass(frozen=True)
class Route:
    action: Literal["expert", "general", "refuse"]
    expert: str | None  # the lead, for `expert`
    consult: tuple[str, ...]  # the other experts the lead may consult
    routed: bool  # True when the router chose the expert, False when the person did
    classification: Classification


def decide(classification: Classification, choice: str = "auto") -> Route:
    """What to do with a question, from its label probabilities and the person's expert choice.

    The scope check runs on every question, so choosing an expert cannot get a medical question
    answered. Consults are the router's call: the other experts whose data the question needs.
    """
    if choice != "auto" and choice not in EXPERTS:
        raise ValueError(f"unknown expert {choice!r}")
    p = classification.probabilities
    if p[OUT_OF_SCOPE] >= REFUSE_AT:
        return Route("refuse", None, (), choice == "auto", classification)
    needs = classification.needs
    ranked = sorted(EXPERT_LABELS, key=lambda label: needs[label], reverse=True)
    if choice != "auto":
        lead, routed = choice, False
    else:
        top = max((*EXPERT_LABELS, GENERAL), key=lambda label: p[label])
        if top == GENERAL or p[top] < LEAD_AT:
            return Route("general", None, (), True, classification)
        lead, routed = top, True
    consult = tuple(e for e in ranked if e != lead and needs[e] >= CONSULT_AT)
    return Route("expert", lead, consult, routed, classification)
