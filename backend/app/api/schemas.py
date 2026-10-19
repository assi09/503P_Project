"""Response models. Field names are camelCase on the wire to match mobile/src/api/types.ts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
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
