"""One day's values next to the person's usual range, and a metric's recent days.

Descriptive only: the usual range is the middle half of the 28 days before, not a test, so a
value outside it is "above usual", never a change or a finding (those come from the screen).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.analysis.evidence import Evidence, ToolError, Window
from app.analysis.screen import without_low_wear

USUAL_DAYS = 28  # the weeks before the day that make up its usual range
MIN_USUAL_DAYS = 7  # fewer days with data and no usual range is given
RECENT_DAYS = 14  # the short trend line beside each value


@dataclass(frozen=True)
class Usual:
    median: float
    low: float  # 25th percentile
    high: float  # 75th percentile
    days: int  # days with data it was computed from


@dataclass(frozen=True)
class DayMetric:
    metric: str
    value: float | None
    usual: Usual | None
    recent: list[float | None]  # the RECENT_DAYS days ending with this one, oldest first


def usual(values: pd.Series) -> Usual | None:
    values = values.dropna()
    if len(values) < MIN_USUAL_DAYS:
        return None
    return Usual(
        median=round(float(values.median()), 2),
        low=round(float(values.quantile(0.25)), 2),
        high=round(float(values.quantile(0.75)), 2),
        days=len(values),
    )


def _value(value: object) -> float | None:
    return None if pd.isna(value) else round(float(value), 2)


# Our own recovery score: where last night's HRV, resting heart rate and time asleep sit among the
# person's previous 28 days, averaged with equal weights. Higher HRV and more sleep count up, a
# higher resting heart rate counts down. An estimate to compare with the morning check-in.
RECOVERY = "recovery_score"
RECOVERY_INPUTS = {"hrv_ms": 1, "resting_hr": -1, "sleep_minutes": 1}
MIN_RECOVERY_INPUTS = 2


def recovery_parts(frame: pd.DataFrame, day: date) -> dict[str, float]:
    """Each input's share (0 to 100) of the 28 days before that the day beat; ties count half."""
    stamp = pd.Timestamp(day)
    if stamp not in frame.index:
        return {}
    before = frame.loc[stamp - pd.Timedelta(days=USUAL_DAYS) : stamp - pd.Timedelta(days=1)]
    parts = {}
    for metric, sign in RECOVERY_INPUTS.items():
        if metric not in frame.columns:
            continue
        value, usual_days = frame.loc[stamp, metric], before[metric].dropna()
        if pd.isna(value) or len(usual_days) < MIN_USUAL_DAYS:
            continue
        beaten = ((usual_days < value).sum() + 0.5 * (usual_days == value).sum()) / len(usual_days)
        parts[metric] = round(100 * (beaten if sign > 0 else 1 - beaten), 1)
    return parts


def recovery_score(parts: dict[str, float]) -> float | None:
    if len(parts) < MIN_RECOVERY_INPUTS:
        return None
    return float(round(sum(parts.values()) / len(parts)))


def with_recovery(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame with the recovery score as one more daily metric."""
    if RECOVERY in frame.columns:
        return frame
    scores = [recovery_score(recovery_parts(frame, stamp.date())) for stamp in frame.index]
    return frame.assign(**{RECOVERY: pd.Series(scores, index=frame.index, dtype=float)})


def day_summary(frame: pd.DataFrame, day: date) -> list[DayMetric]:
    """Every metric on `day`, with its usual range from the USUAL_DAYS days before it.

    Activity totals on low-wear days are left out of the usual range and the trend line (as in
    the screen), but the day's own value is shown as it is; the caller flags a low-wear day.
    """
    frame = with_recovery(frame)
    cleaned = without_low_wear(frame)
    stamp = pd.Timestamp(day)
    before = cleaned.loc[stamp - pd.Timedelta(days=USUAL_DAYS) : stamp - pd.Timedelta(days=1)]
    recent_index = pd.date_range(stamp - pd.Timedelta(days=RECENT_DAYS - 1), stamp)
    recent = cleaned.reindex(recent_index)
    row = frame.loc[stamp] if stamp in frame.index else None
    return [
        DayMetric(
            metric=metric,
            value=_value(row[metric]) if row is not None else None,
            usual=usual(before[metric]),
            recent=[_value(v) for v in recent[metric]],
        )
        for metric in frame.columns
    ]


def series(
    frame: pd.DataFrame, metric: str, end: date, days: int
) -> list[tuple[date, float | None]]:
    """The metric's daily values for the `days` days ending on `end`; gaps stay as None."""
    cleaned = without_low_wear(with_recovery(frame) if metric == RECOVERY else frame)
    index = pd.date_range(pd.Timestamp(end) - pd.Timedelta(days=days - 1), pd.Timestamp(end))
    values = cleaned[metric].reindex(index)
    return [(stamp.date(), _value(value)) for stamp, value in values.items()]


def usual_before(frame: pd.DataFrame, metric: str, day: date) -> Usual | None:
    cleaned = without_low_wear(with_recovery(frame) if metric == RECOVERY else frame)
    stamp = pd.Timestamp(day)
    return usual(
        cleaned[metric].loc[stamp - timedelta(days=USUAL_DAYS) : stamp - timedelta(days=1)]
    )


def compare_day(frame: pd.DataFrame, metric: str, day: date) -> Evidence:
    """One day's value against the person's usual range: the middle half of the 28 days before.

    Descriptive, like the Today screen: "above usual" says where the day sits, not that anything
    changed. Sufficient only with a value that day and at least MIN_USUAL_DAYS days before it.
    """
    if metric not in frame.columns:
        raise ToolError(f"Unknown metric {metric!r}")
    stamp = pd.Timestamp(day)
    if stamp not in frame.index:
        raise ToolError(f"There is no data for {day.isoformat()}")
    value = _value(frame.loc[stamp, metric])
    window = Window(start=day - timedelta(days=USUAL_DAYS), end=day - timedelta(days=1))
    range_ = usual_before(frame, metric, day)
    stats: dict = {"value": value, "usual_days": range_.days if range_ else 0}
    if range_:
        stats |= {"usual_median": range_.median, "usual_low": range_.low, "usual_high": range_.high}
    if value is not None and range_:
        stats["position"] = (
            "above" if value > range_.high else "below" if value < range_.low else "within"
        )
    return Evidence(
        tool="compare_day",
        metrics=(metric,),
        windows=(Window(start=day, end=day), window),
        n=stats["usual_days"],
        sufficient="position" in stats,
        stats=stats,
    )
