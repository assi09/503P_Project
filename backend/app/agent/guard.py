"""A check by meaning that nothing shown to the person diagnoses or gives health advice.

The router only judges the question: an in-scope question ("why is my HRV low?") can still get an
answer that advises ("cutting caffeine should help") or names a condition. The verifier's word
check misses anything phrased in other words, so before an answer is shown, every sentence that
passed the deterministic checks is put to Jev in one call, with one yes/no per sentence. A flagged
sentence is rejected like any other verifier failure: sent back once, then dropped.

If Jev cannot be reached, the word check alone applies, and the trace records that the guard did
not run. The guard never sees data: only the sentences that would be shown.
"""

from dataclasses import dataclass
from typing import Protocol

from app.agent.jev import JevClient, JevError, clean

FLAG_AT = 0.5
MAX_TEXTS = 8  # a summary and at most five claims, with room to spare

INSTRUCTIONS = (
    "Below is a list of sentences an app shows a person about their own Fitbit data. The app may "
    "only describe patterns in the data. Does sentence {i} diagnose, name a medical condition, "
    "or tell the person what to do for their health (treatment, medication, supplements, seeing "
    "a doctor, or changing a habit)? Describing what the data shows, including what went with "
    "what, is not advice."
)
REASON = (
    "gives health advice or names a medical condition; describe only what the data shows, without "
    "telling the person what to do"
)


class GuardError(RuntimeError):
    """The guard could not judge the sentences; the message is safe to show and to log."""


@dataclass(frozen=True)
class Judgement:
    flagged: tuple[bool, ...]  # one per sentence, in order
    probabilities: tuple[float, ...]
    latency_s: float = 0.0
    cost_usd: float = 0.0


class Guard(Protocol):
    def judge(self, texts: list[str]) -> Judgement: ...


class JevGuard:
    def __init__(self, jev: JevClient):
        self._jev = jev

    @staticmethod
    def payload(texts: list[str], model: str = "jev-latest") -> dict:
        sentences = [clean(t) for t in texts]
        return {
            "state": {"sentences": {str(i): t for i, t in enumerate(sentences)}},
            "model": model,
            "questions": {
                f"advice_{i}": {"type": "noul", "instructions": INSTRUCTIONS.format(i=i)}
                for i in range(len(sentences))
            },
        }

    def judge(self, texts: list[str]) -> Judgement:
        if not texts:
            return Judgement((), ())
        if len(texts) > MAX_TEXTS:
            raise GuardError(f"At most {MAX_TEXTS} sentences can be checked at once.")
        try:
            body, latency, cost = self._jev.call(self.payload(texts, self._jev.model))
        except JevError as exc:
            raise GuardError(str(exc)) from exc
        try:
            answers = body["answers"]
            probabilities = tuple(float(answers[f"advice_{i}"]["noul"]) for i in range(len(texts)))
        except (KeyError, TypeError, ValueError) as exc:
            raise GuardError("Jev's answer was not in the expected format.") from exc
        if not all(0 <= p <= 1 for p in probabilities):
            raise GuardError("Jev returned an invalid probability.")
        flagged = tuple(p >= FLAG_AT for p in probabilities)
        return Judgement(flagged, probabilities, latency, cost)
