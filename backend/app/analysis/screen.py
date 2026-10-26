"""Screen every metric for a change between the most recent days and the weeks before.

This is the deterministic first pass: it decides which metrics changed enough to report. Because
around twenty metrics are tested at once, p-values are adjusted with Benjamini-Hochberg so the
share of reported changes that are just noise stays near `FDR`.
"""

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from app.analysis.evidence import Evidence, Window
from app.analysis.tools import LOW_WEAR_MINUTES, compare_windows

RECENT_DAYS = 14
BASELINE_DAYS = 28
FDR = 0.05
MIN_EFFECT = 0.33  # |Cliff's delta| of at least a medium effect

# Totals that only count while the device is worn: low-wear days would look like real drops.
WEAR_DEPENDENT = (
    "steps",
    "calories",
    "distance_km",
    "active_zone_minutes",
    "cardio_load",
    "sedentary_minutes",
    "lightly_active_minutes",
    "moderately_active_minutes",
    "very_active_minutes",
    "hr_zone_light_minutes",
    "hr_zone_moderate_minutes",
    "hr_zone_vigorous_minutes",
    "hr_zone_peak_minutes",
    "strain",
)

# Data-quality signals and columns derived from others are not findings in themselves; the
# inputs of the strain and stress scores are read through the scores.
NOT_SCREENED = (
    "wear_minutes",
    "time_in_bed",
    "hr_zone_light_minutes",
    "hr_zone_moderate_minutes",
    "hr_zone_vigorous_minutes",
    "hr_zone_peak_minutes",
    "still_minutes",
    "still_hr_above_resting",
)


@dataclass(frozen=True)
class Change:
    metric: str
    evidence: Evidence
    q_value: float  # Benjamini-Hochberg adjusted p-value


@dataclass(frozen=True)
class Screen:
    recent: Window
    baseline: Window
    changes: list[Change]  # strongest effect first
    tested: list[Evidence]  # every comparison that was run


def screen_windows(frame: pd.DataFrame) -> tuple[Window, Window]:
    """The last `RECENT_DAYS` of data and the `BASELINE_DAYS` before them."""
    end = frame.index.max().date()
    recent = Window(start=end - timedelta(days=RECENT_DAYS - 1), end=end)
    baseline_end = recent.start - timedelta(days=1)
    baseline = Window(start=baseline_end - timedelta(days=BASELINE_DAYS - 1), end=baseline_end)
    return recent, baseline


def without_low_wear(frame: pd.DataFrame) -> pd.DataFrame:
    """Blank wear-dependent totals on days the device was barely worn."""
    if "wear_minutes" not in frame.columns:
        return frame
    cleaned = frame.copy()
    low = cleaned["wear_minutes"] < LOW_WEAR_MINUTES
    columns = [c for c in WEAR_DEPENDENT if c in cleaned.columns]
    cleaned.loc[low, columns] = float("nan")
    return cleaned


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Adjusted p-values (q-values), in the same order as the input."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        adjusted[i] = running
    return adjusted


def screen(frame: pd.DataFrame) -> Screen:
    recent, baseline = screen_windows(frame)
    cleaned = without_low_wear(frame)
    tested = [
        compare_windows(cleaned, metric, recent, baseline)
        for metric in cleaned.columns
        if metric not in NOT_SCREENED
    ]
    usable = [e for e in tested if e.sufficient and e.stats["p_value"] is not None]
    q_values = benjamini_hochberg([e.stats["p_value"] for e in usable])
    # Record the adjustment in the evidence itself, so what is shown is what was decided on.
    adjusted = {
        e.id: e.model_copy(
            update={"stats": {**e.stats, "p_value_adjusted": q, "metrics_tested": len(usable)}}
        )
        for e, q in zip(usable, q_values, strict=True)
    }
    tested = [adjusted.get(e.id, e) for e in tested]
    changes = [
        Change(metric=e.metrics[0], evidence=e, q_value=e.stats["p_value_adjusted"])
        for e in adjusted.values()
        if e.stats["p_value_adjusted"] < FDR and abs(e.stats["cliffs_delta"]) >= MIN_EFFECT
    ]
    changes.sort(key=lambda c: abs(c.evidence.stats["cliffs_delta"]), reverse=True)
    return Screen(recent=recent, baseline=baseline, changes=changes, tested=tested)
