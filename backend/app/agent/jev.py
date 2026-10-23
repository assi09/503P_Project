"""The HTTP client for Jev, TypeSafe's typed decision model, shared by the router and the guard.

One endpoint (`POST /v1/systemone`): a state and typed questions in, typed answers out. Calls have a
short timeout and no retries, because both callers have a fallback that is better than waiting.
Error bodies may repeat what was sent, so only the status is kept. Nothing here knows about the
agent, so it can be imported from anywhere.
"""

import re
import time
from collections.abc import Callable

import httpx2

JEV_URL = "https://api.typesafe.ai"
JEV_PATH = "/v1/systemone"
JEV_TIMEOUT_S = 2.0  # past this the caller's fallback answers instead
JEV_PRICE_PER_MILLION_INPUT = 0.042  # output tokens are free
MAX_TEXT_CHARS = 500

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class JevError(RuntimeError):
    """Jev could not be used; the message is safe to show and to log."""


def clean(text: str) -> str:
    """What leaves the server: text without control characters, length-limited."""
    return CONTROL.sub(" ", text).strip()[:MAX_TEXT_CHARS]


class JevClient:
    def __init__(
        self,
        api_key: str,
        http: httpx2.Client | None = None,
        model: str = "jev-latest",
        base_url: str = JEV_URL,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not api_key.strip():
            raise JevError("No TypeSafe key: set FA_TYPESAFE_API_KEY in .env.")
        self._key = api_key.strip()
        self._http = http or httpx2.Client(timeout=JEV_TIMEOUT_S)
        self.model = model
        self._url = base_url.rstrip("/") + JEV_PATH
        self._clock = clock

    @classmethod
    def from_settings(cls, settings) -> "JevClient":
        key = settings.typesafe_api_key
        return cls(
            key.get_secret_value() if key else "",
            model=settings.typesafe_model,
            base_url=settings.typesafe_base_url,
        )

    def call(self, payload: dict) -> tuple[dict, float, float]:
        """Posts one request; returns the body, its latency in seconds and its cost in dollars."""
        started = self._clock()
        try:
            response = self._http.post(
                self._url, json=payload, headers={"Authorization": f"Bearer {self._key}"}
            )
        except httpx2.TimeoutException as exc:
            raise JevError("Jev took too long to answer.") from exc
        except httpx2.TransportError as exc:
            raise JevError("Could not reach Jev.") from exc
        if response.status_code in (401, 403):
            raise JevError("TypeSafe rejected the API key.")
        if response.status_code == 429:
            raise JevError("Jev is rate limiting or the account is out of credit.")
        if not response.is_success:
            raise JevError(f"Jev returned an error ({response.status_code}).")
        try:
            body = response.json()
        except ValueError as exc:
            raise JevError("Jev's answer was not in the expected format.") from exc
        if not isinstance(body, dict):
            raise JevError("Jev's answer was not in the expected format.")
        usage = body.get("usage") or {}
        cost = (usage.get("input_tokens") or 0) * JEV_PRICE_PER_MILLION_INPUT / 1_000_000
        return body, self._clock() - started, cost
