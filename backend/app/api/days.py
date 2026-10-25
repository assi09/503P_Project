"""One day's numbers next to the person's usual, and a metric's recent days, for Today."""

from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.analysis import day as days
from app.analysis.tools import LOW_WEAR_MINUTES
from app.api import schemas
from app.api.auth import Now
from app.api.errors import ApiError
from app.api.store import LoadedData, get_data
from app.config import settings

router = APIRouter(tags=["days"])
Data = Annotated[LoadedData, Depends(get_data)]


def _usual(usual: days.Usual | None) -> schemas.Usual | None:
    return schemas.Usual(**vars(usual)) if usual else None


def _range(data: LoadedData) -> tuple[date, date]:
    index = data.daily.frame.index
    return index.min().date(), index.max().date()


@router.get("/days/latest", response_model=schemas.Day)
def get_latest_day(data: Data, clock: Now) -> schemas.Day:
    """The newest day with data: what Today opens on."""
    return get_day(_range(data)[1], data, clock)


@router.get("/days/{day}", response_model=schemas.Day)
def get_day(day: date, data: Data, clock: Now) -> schemas.Day:
    first, last = _range(data)
    if not first <= day <= last:
        raise ApiError(404, "no_data", "There is no data for that day.")
    frame = data.daily.frame
    wear = frame["wear_minutes"].get(pd.Timestamp(day)) if "wear_minutes" in frame else None
    return schemas.Day(
        date=day,
        partial=day == clock.astimezone(ZoneInfo(settings.timezone)).date(),
        low_wear=bool(pd.notna(wear) and wear < LOW_WEAR_MINUTES),
        first=first,
        last=last,
        metrics=[
            schemas.DayMetric(
                metric=m.metric, value=m.value, usual=_usual(m.usual), recent=m.recent
            )
            for m in days.day_summary(frame, day)
        ],
    )


@router.get("/metrics/{metric}", response_model=schemas.MetricSeries)
def get_metric(
    metric: str,
    data: Data,
    end: date | None = None,
    span: Annotated[int, Query(alias="days", ge=7, le=366)] = 30,
) -> schemas.MetricSeries:
    frame = data.daily.frame
    if metric not in frame.columns:
        raise ApiError(404, "unknown_metric", "There is no such metric.")
    first, last = _range(data)
    end = min(end or last, last)
    if end < first:
        raise ApiError(404, "no_data", "There is no data for that day.")
    return schemas.MetricSeries(
        metric=metric,
        points=[schemas.Point(date=d, value=v) for d, v in days.series(frame, metric, end, span)],
        usual=_usual(days.usual_before(frame, metric, end)),
    )
