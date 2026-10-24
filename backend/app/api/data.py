"""Endpoints about the user's data itself: where it comes from and how complete it is."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.analysis.evidence import Window
from app.analysis.tools import coverage
from app.api import schemas
from app.api.store import LoadedData, get_data

router = APIRouter(prefix="/data", tags=["data"])

# Metrics shown on the Data screen, in display order.
COVERAGE_METRICS = {
    "steps": "Steps",
    "sleep_minutes": "Sleep",
    "resting_hr": "Resting heart rate",
    "hrv_ms": "HRV",
    "readiness": "Readiness",
    "sleep_score": "Sleep score",
    "skin_temp_variation_c": "Skin temperature",
}


@router.get("/status", response_model=schemas.DataStatus)
def data_status(data: Annotated[LoadedData, Depends(get_data)]) -> schemas.DataStatus:
    frame = data.daily.frame
    window = Window(start=frame.index.min().date(), end=frame.index.max().date())
    stats = coverage(frame, window).stats
    present = stats["fraction_present"]
    return schemas.DataStatus(
        source=data.source,
        last_sync=data.loaded_at,
        range=schemas.Window(start=window.start, end=window.end),
        coverage=[
            schemas.MetricCoverage(metric=metric, label=label, fraction_present=present[metric])
            for metric, label in COVERAGE_METRICS.items()
            if metric in present
        ],
        low_wear_days=stats.get("low_wear_days", []),
    )
