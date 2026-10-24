"""Google Health writes without retries: a failed response can hide a successful create."""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx2

from app.actions.schemas import DATA_TYPES
from app.sync.client import API_BASE


@dataclass(frozen=True)
class Outcome:
    status: Literal["succeeded", "failed", "unknown"]
    provider_name: str | None = None
    operation_name: str | None = None
    error: str | None = None


class Writer(Protocol):
    def create(self, kind: str, payload: dict) -> Outcome: ...
    def delete(self, kind: str, name: str) -> Outcome: ...


def valid_name(name: object, kind: str) -> bool:
    return (
        isinstance(name, str)
        and len(name) <= 512
        and bool(
            re.fullmatch(
                rf"users/[A-Za-z0-9_-]+/dataTypes/{DATA_TYPES[kind]}/dataPoints/[A-Za-z0-9_-]+",
                name,
            )
        )
    )


class GoogleWriter:
    def __init__(self, token: str, http: httpx2.Client | None = None):
        self._token = token
        self._owns_http = http is None
        self._http = http or httpx2.Client(timeout=20)

    def create(self, kind: str, payload: dict) -> Outcome:
        return self._post(kind, f"{API_BASE}/{DATA_TYPES[kind]}/dataPoints", payload)

    def delete(self, kind: str, name: str) -> Outcome:
        if not valid_name(name, kind):
            return Outcome("failed", error="The stored record reference is invalid.")
        return self._post(
            kind,
            f"{API_BASE}/{DATA_TYPES[kind]}/dataPoints:batchDelete",
            {"names": [name]},
            deleting=True,
        )

    def _post(self, kind: str, url: str, payload: dict, deleting: bool = False) -> Outcome:
        try:
            return self._send(kind, url, payload, deleting)
        finally:
            if self._owns_http:
                self._http.close()

    def _send(self, kind: str, url: str, payload: dict, deleting: bool) -> Outcome:
        try:
            response = self._http.post(
                url, json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx2.TransportError:
            return Outcome("unknown", error="Google did not confirm the outcome. Do not retry.")
        if response.status_code in {400, 401, 403, 404, 422, 429}:
            return Outcome("failed", error="Google rejected the request. No success was confirmed.")
        if not response.is_success:
            return Outcome("unknown", error="Google did not confirm the outcome. Do not retry.")
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return Outcome("unknown", error="Google returned an unrecognised result.")
        operation = body.get("name")
        operation = operation if isinstance(operation, str) and len(operation) <= 512 else None
        if body.get("done") is not True:
            return Outcome(
                "unknown",
                operation_name=operation,
                error="Google has not confirmed completion. Do not retry.",
            )
        if "error" in body:
            failure = body["error"]
            code = failure.get("code") if isinstance(failure, dict) else None
            # Only definite validation/auth/resource rejection is safe to offer for revision.
            # Internal failures or malformed union results may hide a completed write.
            rejected = type(code) is int and code in (3, 5, 7, 16) and "response" not in body
            return Outcome(
                "failed" if rejected else "unknown",
                operation_name=operation,
                error="Google rejected the operation."
                if rejected
                else "Google did not confirm the outcome. Do not retry.",
            )
        result = body.get("response")
        if not isinstance(result, dict):
            return Outcome(
                "unknown", operation_name=operation, error="Google returned no completed result."
            )
        if deleting:
            return Outcome("succeeded", operation_name=operation)
        name = result.get("name")
        if not valid_name(name, kind):
            return Outcome(
                "unknown",
                operation_name=operation,
                error="Google returned no usable record reference.",
            )
        return Outcome("succeeded", provider_name=name, operation_name=operation)
