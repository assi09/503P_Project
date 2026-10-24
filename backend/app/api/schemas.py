"""Response models. Field names are camelCase on the wire to match mobile/src/api/types.ts."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Window(ApiModel):
    start: date
    end: date


class MetricCoverage(ApiModel):
    metric: str
    label: str
    fraction_present: float


class DataStatus(ApiModel):
    source: Literal["takeout", "google_health", "none"]
    last_sync: datetime | None
    range: Window | None
    coverage: list[MetricCoverage]
    low_wear_days: list[date]


class ErrorBody(ApiModel):
    code: str
    message: str


class ErrorResponse(ApiModel):
    error: ErrorBody


class Evidence(ApiModel):
    id: str
    tool: str
    metrics: list[str]
    windows: list[Window]
    n: int
    sufficient: bool
    stats: dict[str, Any]  # keys stay snake_case: they are statistic names, not fields


class Point(ApiModel):
    date: date
    value: float | None


class Finding(ApiModel):
    id: str
    title: str
    summary: str
    metric: str
    unit: str
    direction: Literal["up", "down", "none"]
    change: str
    series: list[Point]
    highlight: Window | None
    evidence_ids: list[str]


class ContextQuestion(ApiModel):
    id: str
    prompt: str
    date: date
    options: list[str]
    answer: str | None


class Report(ApiModel):
    id: str
    period: Window
    created_at: datetime
    headline: str
    findings: list[Finding]
    questions: list[ContextQuestion]
    evidence: dict[str, Evidence]


class Credentials(ApiModel):
    # Loose limits here; the account rules give the person a specific message.
    email: str = Field(max_length=1000)
    password: str = Field(max_length=1000)


class Account(ApiModel):
    email: str
    status: Literal["pending", "approved", "rejected"]
    is_admin: bool


class SignedIn(ApiModel):
    token: str
    account: Account


class AccessRequest(ApiModel):
    id: str
    email: str
    requested_at: datetime


class ChatMessage(ApiModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    evidence_ids: list[str]
    attachment: dict[str, Any] | None = None  # what a question asked about
    answered_by: str | None = None  # an expert or "general"; absent on refusals
    routed: bool | None = None  # true if the router chose the expert
    consulted: list[str] | None = None
    refused: bool | None = None
    created_at: datetime


class GoogleStatus(ApiModel):
    status: Literal["none", "active", "reconnect_needed"]
    syncing: bool
    last_sync: datetime | None
    last_error: str | None  # the latest sync's failure, safe to show
    missing_scopes: list[str]  # permissions the person unticked on Google's page


class ConnectStart(ApiModel):
    url: str  # Google's sign-in page, to open in the browser
