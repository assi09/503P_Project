"""Deterministic analysis tools over a daily metrics table.

Tools never call a model. Each one validates its arguments, computes its statistics on the
non-missing days in the requested windows, and returns an `Evidence` record.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

from app.analysis.evidence import Evidence, ToolError, Window

MIN_DAYS_DESCRIBE = 3
MIN_DAYS_COMPARE = 7  # per window
LOW_WEAR_MINUTES = 600  # under 10 hours of wear, activity totals are not representative


def _round(value: float, digits: int = 4) -> float | None:
    value = float(value)
    return None if math.isnan(value) else round(value, digits)


def _values(frame: pd.DataFrame, metric: str, window: Window) -> pd.Series:
    if metric not in frame.columns:
        raise ToolError(f"Unknown metric {metric!r}")
    rows = frame.loc[pd.Timestamp(window.start) : pd.Timestamp(window.end), metric]
    return rows.dropna()


def describe(frame: pd.DataFrame, metric: str, window: Window) -> Evidence:
    """Summary statistics of one metric over one window."""
    values = _values(frame, metric, window)
    summary = {
        "mean": _round(values.mean()),
        "median": _round(values.median()),
        "sd": _round(values.std()),
        "min": _round(values.min()),
        "max": _round(values.max()),
        "missing_days": window.days - len(values),
    }
    return Evidence(
        tool="describe",
        metrics=(metric,),
        windows=(window,),
        n=len(values),
        sufficient=len(values) >= MIN_DAYS_DESCRIBE,
        stats=summary,
    )


def coverage(frame: pd.DataFrame, window: Window) -> Evidence:
    """How complete each metric is over a window, and how many days had low wear time."""
    rows = frame.loc[pd.Timestamp(window.start) : pd.Timestamp(window.end)]
    present = {metric: int(rows[metric].notna().sum()) for metric in frame.columns}
    summary: dict = {
        "days": window.days,
        "fraction_present": {m: _round(count / window.days, 3) for m, count in present.items()},
    }
    if "wear_minutes" in frame.columns:
        low = rows.index[rows["wear_minutes"] < LOW_WEAR_MINUTES]
        summary["low_wear_days"] = [day.date().isoformat() for day in low]
    return Evidence(
        tool="coverage",
        metrics=tuple(frame.columns),
        windows=(window,),
        n=len(rows),
        sufficient=True,
        stats=summary,
    )


def compare_windows(frame: pd.DataFrame, metric: str, recent: Window, baseline: Window) -> Evidence:
    """Whether a metric differs between two non-overlapping windows.

    Uses a two-sided Mann-Whitney U test, which assumes no particular distribution, and reports
    Cliff's delta as the effect size (-1..1, share of pairs where recent > baseline minus the
    reverse).
    """
    if recent.start <= baseline.end and baseline.start <= recent.end:
        raise ToolError("recent and baseline windows overlap")
    a, b = _values(frame, metric, recent), _values(frame, metric, baseline)
    sufficient = min(len(a), len(b)) >= MIN_DAYS_COMPARE
    summary = {
        "mean_recent": _round(a.mean()),
        "mean_baseline": _round(b.mean()),
        "difference": _round(a.mean() - b.mean()),
        "pct_change": _round(100 * (a.mean() - b.mean()) / abs(b.mean()), 2)
        if len(b) and b.mean() != 0
        else None,
        "n_recent": len(a),
        "n_baseline": len(b),
        "cliffs_delta": None,
        "p_value": None,
    }
    if len(a) and len(b):
        if np.ptp(np.concatenate([a, b])) == 0:
            summary["cliffs_delta"], summary["p_value"] = 0.0, 1.0
        else:
            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            summary["cliffs_delta"] = _round(2 * u / (len(a) * len(b)) - 1)
            summary["p_value"] = _round(p, 6)
    return Evidence(
        tool="compare_windows",
        metrics=(metric,),
        windows=(recent, baseline),
        n=len(a) + len(b),
        sufficient=sufficient,
        stats=summary,
    )
