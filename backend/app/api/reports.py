"""Endpoints for the analysis: the latest report and the evidence behind it."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.analysis import report as analysis_report
from app.analysis.evidence import Evidence
from app.api import schemas
from app.api.store import LoadedData, get_data

router = APIRouter(tags=["reports"])


def _window(window) -> schemas.Window:
    return schemas.Window(start=window.start, end=window.end)


def _evidence(evidence: Evidence) -> schemas.Evidence:
    return schemas.Evidence(
        id=evidence.id,
        tool=evidence.tool,
        metrics=list(evidence.metrics),
        windows=[_window(w) for w in evidence.windows],
        n=evidence.n,
        sufficient=evidence.sufficient,
        stats=evidence.stats,
    )


def _finding(finding: analysis_report.Finding) -> schemas.Finding:
    return schemas.Finding(
        id=finding.id,
        title=finding.title,
        summary=finding.summary,
        metric=finding.metric,
        unit=finding.unit,
        direction=finding.direction,
        change=finding.change,
        series=[schemas.Point(date=day, value=value) for day, value in finding.series],
        highlight=_window(finding.highlight),
        evidence_ids=finding.evidence_ids,
    )


@router.get("/reports/latest", response_model=schemas.Report)
def latest_report(data: Annotated[LoadedData, Depends(get_data)]) -> schemas.Report:
    report = data.report
    return schemas.Report(
        id=f"report_{report.period.end.isoformat()}",
        period=_window(report.period),
        created_at=report.created_at,
        headline=report.headline,
        findings=[_finding(f) for f in report.findings],
        questions=[],
        evidence={key: _evidence(e) for key, e in report.evidence.items()},
    )


@router.get("/evidence/{evidence_id}", response_model=schemas.Evidence)
def get_evidence(evidence_id: str, data: Annotated[LoadedData, Depends(get_data)]):
    evidence = data.evidence.get(evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="This evidence does not exist.")
    return _evidence(evidence)
