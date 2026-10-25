"""One day's values next to the person's usual range, and a metric's recent days.

Descriptive only: the usual range is the middle half of the 28 days before, not a test, so a
value outside it is "above usual", never a change or a finding (those come from the screen).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

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


def day_summary(frame: pd.DataFrame, day: date) -> list[DayMetric]:
    """Every metric on `day`, with its usual range from the USUAL_DAYS days before it.

    Activity totals on low-wear days are left out of the usual range and the trend line (as in
    the screen), but the day's own value is shown as it is; the caller flags a low-wear day.
    """
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
    cleaned = without_low_wear(frame)
    index = pd.date_range(pd.Timestamp(end) - pd.Timedelta(days=days - 1), pd.Timestamp(end))
    values = cleaned[metric].reindex(index)
    return [(stamp.date(), _value(value)) for stamp, value in values.items()]


def usual_before(frame: pd.DataFrame, metric: str, day: date) -> Usual | None:
    cleaned = without_low_wear(frame)
    stamp = pd.Timestamp(day)
    return usual(
        cleaned[metric].loc[stamp - timedelta(days=USUAL_DAYS) : stamp - timedelta(days=1)]
    )
