"""Routing a question to the expert that owns its topic.

A classifier gives a probability for each label: one per expert, `general`, and `out_of_scope`.
Code, not the classifier, decides what to do with them (`decide`): refuse, hand the question to the
general agent, or give it to the most likely expert, which may consult the other likely ones.

Jev (TypeSafe's typed decision model) is the classifier in the app. If it fails or times out, a
keyword rule over metric names routes instead, so a question is never lost to the router. An LLM
router exists for the evaluation, to compare accuracy, latency and cost. Every router receives the
question text only, never the person's data or memory.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, Protocol

import httpx2

from app.agent.experts import EXPERTS
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
    "A person asks a question about their own Fitbit data. Which topic is the question about?"
)
MAX_QUESTION_CHARS = 500

# Thresholds on the probabilities. Tuned by the router evaluation, not fitted to anyone's data.
REFUSE_AT = 0.5  # out of scope at least this likely: refuse
LEAD_AT = 0.4  # the most likely expert must reach this, or the general agent answers
CONSULT_AT = 0.25  # other experts this likely are consulted by the lead

JEV_URL = "https://api.typesafe.ai"
JEV_PATH = "/v1/systemone"
JEV_TIMEOUT_S = 2.0  # routing must be fast: past this the keyword rule answers instead
JEV_PRICE_PER_MILLION_INPUT = 0.042  # output tokens are free

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class RouterError(RuntimeError):
    """A classifier could not label the question; the message is safe to show and to log."""


@dataclass(frozen=True)
class Classification:
    probabilities: dict[str, float]  # every label, summing to 1
    source: str  # jev, keyword, llm
    latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None  # why an earlier router in the chain failed

    @property
    def top(self) -> str:
        return max(LABELS, key=lambda label: self.probabilities[label])


class Router(Protocol):
    def classify(self, question: str) -> Classification: ...


def clean(question: str) -> str:
    """What leaves the server: the question only, without control characters, length-limited."""
    return CONTROL.sub(" ", question).strip()[:MAX_QUESTION_CHARS]


def normalized(raw: dict) -> dict[str, float]:
    """Probabilities over every label, summing to 1. Raises `RouterError` on unusable values."""
    if not isinstance(raw, dict):
        raise RouterError("The router returned no probabilities.")
    values = {}
    for label in LABELS:
        value = raw.get(label, 0.0)
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
            raise RouterError(f"The router returned an invalid probability for {label}.")
        values[label] = float(value)
    total = sum(values.values())
    if total <= 0:
        raise RouterError("The router returned no probabilities.")
    return {label: value / total for label, value in values.items()}


class JevRouter:
    def __init__(
        self,
        api_key: str,
        http: httpx2.Client | None = None,
        model: str = "jev-latest",
        base_url: str = JEV_URL,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not api_key.strip():
            raise RouterError("No TypeSafe key: set FA_TYPESAFE_API_KEY in .env.")
        self._key = api_key.strip()
        # No retries: a slow or failing call falls back to the keyword rule instead.
        self._http = http or httpx2.Client(timeout=JEV_TIMEOUT_S)
        self._model = model
        self._url = base_url.rstrip("/") + JEV_PATH
        self._clock = clock

    @classmethod
    def from_settings(cls, settings) -> "JevRouter":
        key = settings.typesafe_api_key
        return cls(
            key.get_secret_value() if key else "",
            model=settings.typesafe_model,
            base_url=settings.typesafe_base_url,
        )

    def payload(self, question: str) -> dict:
        return {
            "state": clean(question),
            "model": self._model,
            "questions": {
                "topic": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}
            },
        }

    def classify(self, question: str) -> Classification:
        started = self._clock()
        try:
            response = self._http.post(
                self._url,
                json=self.payload(question),
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx2.TimeoutException as exc:
            raise RouterError("Jev took too long to answer.") from exc
        except httpx2.TransportError as exc:
            raise RouterError("Could not reach Jev.") from exc
        # Error bodies may repeat the question, so only the status is kept.
        if response.status_code in (401, 403):
            raise RouterError("TypeSafe rejected the API key.")
        if response.status_code == 429:
            raise RouterError("Jev is rate limiting or the account is out of credit.")
        if not response.is_success:
            raise RouterError(f"Jev returned an error ({response.status_code}).")
        try:
            body = response.json()
            answer = body["answers"]["topic"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RouterError("Jev's answer was not in the expected format.") from exc
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise RouterError("Jev's answer was not in the expected format.")
        probabilities = normalized(answer.get("probabilities"))
        usage = body.get("usage") or {}
        input_tokens = usage.get("input_tokens") or 0
        return Classification(
            probabilities,
            source="jev",
            latency_s=self._clock() - started,
            cost_usd=input_tokens * JEV_PRICE_PER_MILLION_INPUT / 1_000_000,
        )


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
# Not "sick" or "ill": "did my HRV drop when I was sick?" is a question about the data.
OFF_TOPIC = _words(r"doctor", r"symptom", r"cure", r"medicine")


class KeywordRouter:
    """Metric words decide the topic; medical words mean out of scope. Free and instant."""

    def classify(self, question: str) -> Classification:
        text = clean(question)
        probabilities = dict.fromkeys(LABELS, 0.0)
        if MEDICAL.search(text) or OFF_TOPIC.search(text):
            probabilities[OUT_OF_SCOPE] = 1.0
            return Classification(probabilities, source="keyword")
        hits = {label: len(pattern.findall(text)) for label, pattern in KEYWORDS.items()}
        total = sum(hits.values())
        if not total:
            probabilities[GENERAL] = 1.0
        else:
            probabilities |= {label: count / total for label, count in hits.items()}
        return Classification(probabilities, source="keyword")


ROUTE_TOOL = "route"
LLM_ROUTER_PROMPT = (
    INSTRUCTIONS
    + " Give the probability of each topic with the route tool; they should sum to 1.\n"
    + "\n".join(f"- {label}: {meaning}" for label, meaning in CRITERIA.items())
)


class LLMRouter:
    """The same labels from the language model, for comparison in the evaluation."""

    def __init__(self, llm: LLM):
        self._llm = llm

    def classify(self, question: str) -> Classification:
        tool = {
            "type": "function",
            "function": {
                "name": ROUTE_TOOL,
                "description": "The probability of each topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        label: {"type": "number", "minimum": 0, "maximum": 1} for label in LABELS
                    },
                    "required": list(LABELS),
                },
            },
        }
        messages = [
            {"role": "system", "content": LLM_ROUTER_PROMPT},
            {"role": "user", "content": json.dumps({"question": clean(question)})},
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
            normalized(call.arguments),
            source="llm",
            latency_s=completion.latency_s,
            cost_usd=completion.cost_usd,
        )


@dataclass(frozen=True)
class FallbackRouter:
    """Tries the primary router; when it fails, the fallback answers and the reason is kept."""

    primary: Router
    fallback: Router

    def classify(self, question: str) -> Classification:
        try:
            return self.primary.classify(question)
        except RouterError as exc:
            return replace(self.fallback.classify(question), error=str(exc))


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
    answered. Consults are the router's call: the other experts likely enough to be involved.
    """
    if choice != "auto" and choice not in EXPERTS:
        raise ValueError(f"unknown expert {choice!r}")
    p = classification.probabilities
    if p[OUT_OF_SCOPE] >= REFUSE_AT:
        return Route("refuse", None, (), choice == "auto", classification)
    ranked = sorted(EXPERT_LABELS, key=lambda label: p[label], reverse=True)
    if choice != "auto":
        lead, routed = choice, False
    else:
        top = max((*EXPERT_LABELS, GENERAL), key=lambda label: p[label])
        if top == GENERAL or p[top] < LEAD_AT:
            return Route("general", None, (), True, classification)
        lead, routed = top, True
    consult = tuple(e for e in ranked if e != lead and p[e] >= CONSULT_AT)
    return Route("expert", lead, consult, routed, classification)
