"""Reading from the Google Health API: paging, date windows, timeouts and retries.

Points are returned as the API sends them; turning them into daily metrics is a separate step.
Errors become `SyncError`s whose messages can be shown to the user as they are.
"""

import time
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import httpx2

from app.sync.google_auth import ReconnectNeeded, SyncError

API_BASE = "https://health.googleapis.com/v4/users/me/dataTypes"
TIMEOUT_S = 30
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF_S = 30

# A daily roll-up covers at most 90 days per request, and only 14 for these types.
ROLLUP_MAX_DAYS = 90
SHORT_ROLLUP_TYPES = {
    "heart-rate",
    "active-minutes",
    "total-calories",
    "calories-in-heart-rate-zone",
}


class ApiError(SyncError):
    """The API refused or failed a request, after any retries."""

    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after  # seconds the server asked us to wait, if it said


def _civil_date(day: date) -> dict:
    return {"date": {"year": day.year, "month": day.month, "day": day.day}}


def _windows(start: date, end: date, max_days: int) -> Iterator[tuple[date, date]]:
    """Splits [start, end) into consecutive windows of at most `max_days` days."""
    while start < end:
        window_end = min(end, start + timedelta(days=max_days))
        yield start, window_end
        start = window_end


class HealthClient:
    def __init__(
        self,
        token: Callable[[], str],
        http: httpx2.Client | None = None,
        max_retries: int = 4,
        backoff_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._token = token
        self._http = http or httpx2.Client(timeout=TIMEOUT_S)
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._sleep = sleep

    def list_points(
        self, data_type: str, filter: str | None = None, page_size: int | None = None
    ) -> Iterator[dict]:
        """Every data point of a type matching `filter`, following pages to the end."""
        params: dict[str, str | int] = {}
        if filter:
            params["filter"] = filter
        if page_size:
            params["pageSize"] = page_size
        while True:
            body = self._request("GET", f"{API_BASE}/{data_type}/dataPoints", params=params)
            yield from body.get("dataPoints", [])
            token = body.get("nextPageToken")
            if not token:
                return
            params = {**params, "pageToken": token}

    def daily_rollup(self, data_type: str, start: date, end: date) -> list[dict]:
        """Per-day totals for the local calendar days in [start, end)."""
        max_days = 14 if data_type in SHORT_ROLLUP_TYPES else ROLLUP_MAX_DAYS
        points: list[dict] = []
        for window_start, window_end in _windows(start, end, max_days):
            request = {
                "range": {"start": _civil_date(window_start), "end": _civil_date(window_end)}
            }
            while True:
                url = f"{API_BASE}/{data_type}/dataPoints:dailyRollUp"
                body = self._request("POST", url, json=request)
                points.extend(body.get("rollupDataPoints", []))
                token = body.get("nextPageToken")
                if not token:
                    break
                request = {**request, "pageToken": token}
        return points

    def _request(self, method: str, url: str, **kwargs) -> dict:
        error: ApiError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(self._delay(attempt, error))
            try:
                response = self._http.request(
                    method, url, headers={"Authorization": f"Bearer {self._token()}"}, **kwargs
                )
            except httpx2.TimeoutException:
                error = ApiError("Google Health took too long to answer.")
                continue
            except httpx2.TransportError:
                error = ApiError("Could not reach Google Health.")
                continue

            if response.status_code in RETRY_STATUSES:
                error = ApiError(_message(response), response.status_code, _retry_after(response))
                continue
            if response.status_code == 401:
                raise ReconnectNeeded(
                    "Google rejected the sign-in; run `python -m app.sync connect`."
                )
            if response.status_code == 403:
                raise ApiError(
                    f"Google Health denied access ({_message(response)}). Was every permission "
                    "granted at sign-in?",
                    403,
                )
            if not response.is_success:
                raise ApiError(_message(response), response.status_code)
            try:
                return response.json()
            except ValueError as exc:
                raise ApiError("Google Health sent a response that is not JSON.") from exc
        assert error is not None
        raise error

    def _delay(self, attempt: int, error: ApiError | None) -> float:
        if error is not None and error.retry_after is not None:
            return min(error.retry_after, MAX_BACKOFF_S)
        return min(self._backoff_s * 2 ** (attempt - 1), MAX_BACKOFF_S)


def _message(response: httpx2.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    return error.get("message") or f"HTTP {response.status_code}"


def _retry_after(response: httpx2.Response) -> float | None:
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
