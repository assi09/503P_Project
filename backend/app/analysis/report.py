"""Turn a screen into a report with plain, templated text.

No language model is involved: every number in the text is read from the evidence it cites. This
is both what the app shows until the agent exists and the "statistics only" baseline the agent
is evaluated against.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd

from app.analysis.evidence import Evidence, Window
from app.analysis.screen import Change, Screen

MAX_FINDINGS = 5


@dataclass(frozen=True)
class MetricInfo:
    label: str
    unit: str  # shown after values; empty for unitless scores
    percent_change: bool = True  # show the change as a percentage of the earlier average


METRICS: dict[str, MetricInfo] = {
    "steps": MetricInfo("Steps", "steps"),
    "calories": MetricInfo("Calories", "kcal"),
    "distance_km": MetricInfo("Distance", "km"),
    "active_zone_minutes": MetricInfo("Active Zone Minutes", "min"),
    "cardio_load": MetricInfo("Cardio load", ""),
    "resting_hr": MetricInfo("Resting heart rate", "bpm", percent_change=False),
    "hrv_ms": MetricInfo("Heart rate variability", "ms"),
    "respiratory_rate": MetricInfo("Breathing rate", "breaths/min", percent_change=False),
    "readiness": MetricInfo("Readiness", "", percent_change=False),
    "sedentary_minutes": MetricInfo("Sedentary time", "min"),
    "lightly_active_minutes": MetricInfo("Light activity", "min"),
    "moderately_active_minutes": MetricInfo("Moderate activity", "min"),
    "very_active_minutes": MetricInfo("Vigorous activity", "min"),
    "sleep_minutes": MetricInfo("Time asleep", "min"),
    "sleep_efficiency": MetricInfo("Sleep efficiency", "%", percent_change=False),
    "bedtime_hour": MetricInfo("Bedtime", "", percent_change=False),
    "sleep_score": MetricInfo("Sleep score", "", percent_change=False),
    "deep_sleep_minutes": MetricInfo("Deep sleep", "min"),
    "light_sleep_minutes": MetricInfo("Light sleep", "min"),
    "rem_sleep_minutes": MetricInfo("REM sleep", "min"),
    "awake_in_bed_minutes": MetricInfo("Awake in bed", "min"),
    "skin_temp_variation_c": MetricInfo("Skin temperature", "°C", percent_change=False),
}


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    summary: str
    metric: str
    unit: str
    direction: Literal["up", "down", "none"]
    change: str
    series: list[tuple[date, float | None]]
    highlight: Window
    evidence_ids: list[str]


@dataclass(frozen=True)
class Report:
    period: Window
    created_at: datetime
    headline: str
    findings: list[Finding]
    evidence: dict[str, Evidence]


def info(metric: str) -> MetricInfo:
    return METRICS.get(metric, MetricInfo(metric.replace("_", " ").capitalize(), ""))


def clock(hours: float) -> str:
    """Bedtime in hours relative to midnight as a clock time: -0.5 -> 23:30."""
    minutes = round((hours % 24) * 60) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_value(metric: str, value: float) -> str:
    if metric == "bedtime_hour":
        return clock(value)
    unit = info(metric).unit
    digits = 0 if abs(value) >= 100 else 1
    number = f"{value:,.{digits}f}"
    if unit == "%":
        return f"{number}%"
    return f"{number} {unit}".rstrip()


def change_label(metric: str, stats: dict) -> str:
    difference = stats["difference"]
    if metric == "bedtime_hour":
        return f"{round(difference * 60):+d} min"
    if info(metric).percent_change and stats.get("pct_change") is not None:
        return f"{stats['pct_change']:+.0f}%"
    digits = 0 if abs(difference) >= 10 else 1
    unit = info(metric).unit
    suffix = "" if unit in ("", "%") else f" {unit}"
    return f"{difference:+.{digits}f}{'%' if unit == '%' else ''}{suffix}"


def _title(metric: str, up: bool) -> str:
    label = info(metric).label
    if metric == "bedtime_hour":
        return "Bedtime moved later" if up else "Bedtime moved earlier"
    return f"{label} went {'up' if up else 'down'}"


def _summary(change: Change, screen: Screen) -> str:
    stats = change.evidence.stats
    metric = change.metric
    label = info(metric).label
    recent = format_value(metric, stats["mean_recent"])
    earlier = format_value(metric, stats["mean_baseline"])
    noun = "Your bedtime" if metric == "bedtime_hour" else f"Your {label[0].lower()}{label[1:]}"
    return (
        f"{noun} averaged {recent} over the last {screen.recent.days} days, "
        f"compared with {earlier} over the {screen.baseline.days} days before."
    )


def _series(frame: pd.DataFrame, metric: str, period: Window) -> list[tuple[date, float | None]]:
    values = frame.loc[pd.Timestamp(period.start) : pd.Timestamp(period.end), metric]
    return [
        (day.date(), None if math.isnan(value) else round(float(value), 3))
        for day, value in values.items()
    ]


def build_report(frame: pd.DataFrame, screen: Screen, created_at: datetime) -> Report:
    period = Window(start=screen.baseline.start, end=screen.recent.end)
    findings = []
    for change in screen.changes[:MAX_FINDINGS]:
        stats = change.evidence.stats
        up = stats["difference"] > 0
        findings.append(
            Finding(
                id=f"f_{change.metric}",
                title=_title(change.metric, up),
                summary=_summary(change, screen),
                metric=change.metric,
                unit=info(change.metric).unit,
                direction="up" if up else "down",
                change=change_label(change.metric, stats),
                series=_series(frame, change.metric, period),
                highlight=screen.recent,
                evidence_ids=[change.evidence.id],
            )
        )
    count = len(findings)
    if count == 0:
        headline = f"Nothing changed enough to report in the last {screen.recent.days} days."
    else:
        things = "change stood" if count == 1 else "changes stood"
        headline = f"{count} {things} out in the last {screen.recent.days} days."
    return Report(
        period=period,
        created_at=created_at,
        headline=headline,
        findings=findings,
        evidence={c.evidence.id: c.evidence for c in screen.changes[:MAX_FINDINGS]},
    )
