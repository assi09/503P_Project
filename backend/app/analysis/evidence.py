"""The record every analysis tool returns, so each claim the agent makes can cite a computation."""

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolError(ValueError):
    """A tool was called with arguments that cannot be computed on this data."""


class Window(BaseModel):
    """An inclusive range of calendar dates."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> "Window":
        if self.start > self.end:
            raise ValueError("window start is after its end")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class Evidence(BaseModel):
    """The inputs and results of one tool call.

    `sufficient` is False when there were too few data points for the statistics to be trusted;
    the stats are still reported, but the agent must not base a claim on them.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    tool: str
    metrics: tuple[str, ...]
    windows: tuple[Window, ...]
    n: int
    sufficient: bool
    stats: dict[str, Any]
