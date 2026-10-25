"""Owned, versioned drafts. A committed compare-and-set claim precedes every remote write.

An interrupted/ambiguous execution is never replayed automatically. These rows are separate from
analysis evidence and memory: they record what a person reviewed, not a statistical finding.
"""

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actions.provider import Outcome, Writer
from app.actions.schemas import LOG
from app.api.errors import ApiError
from app.db.models import HealthAction, HealthActionEvent


def get(db: Session, user_id: uuid.UUID, action_id: uuid.UUID) -> HealthAction:
    row = db.scalar(
        select(HealthAction).where(HealthAction.id == action_id, HealthAction.user_id == user_id)
    )
    if row is None:
        raise ApiError(404, "not_found", "No such logging draft.")
    return row


def history(db: Session, user_id: uuid.UUID) -> list[HealthAction]:
    return list(
        db.scalars(
            select(HealthAction)
            .where(HealthAction.user_id == user_id)
            .order_by(HealthAction.created_at.desc(), HealthAction.id)
            .limit(100)
        )
    )


def _event(db: Session, row: HealthAction, event: str, now: datetime) -> None:
    db.add(
        HealthActionEvent(
            user_id=row.user_id,
            action_id=row.id,
            version=row.version,
            event=event,
            payload=copy.deepcopy(row.payload),
            created_at=now,
        )
    )


def _payload(payload: dict) -> dict:
    try:
        return LOG.validate_python(payload).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    except ValidationError:
        # Validation errors can contain the original personal input; never echo them.
        raise ApiError(
            422, "invalid_log", "Check the log fields, units and timezone-aware times."
        ) from None


def _given(payload: dict) -> dict:
    # The tracker's reading can change between two identical requests as data syncs.
    return {key: value for key, value in payload.items() if key != "measured"}


def _fingerprint(payload: dict) -> str:
    keys = (
        ("kind", "foodName", "consumedAt")
        if payload["kind"] == "food"
        else ("kind", "exerciseType", "startTime", "endTime")
    )
    canonical = {key: payload[key] for key in keys}
    for field in ("consumedAt", "startTime", "endTime"):
        if field in canonical:
            canonical[field] = datetime.fromisoformat(canonical[field]).astimezone(UTC).isoformat()
    if "foodName" in canonical:
        canonical["foodName"] = " ".join(canonical["foodName"].casefold().split())
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def _duplicate(
    db: Session, user_id: uuid.UUID, fingerprint: str, excluding: uuid.UUID | None = None
) -> None:
    query = select(HealthAction).where(
        HealthAction.user_id == user_id,
        HealthAction.fingerprint == fingerprint,
        HealthAction.status.not_in(("cancelled", "undone")),
    )
    if excluding is not None:
        query = query.where(HealthAction.id != excluding)
    if db.scalar(query) is not None:
        raise ApiError(409, "duplicate_log", "This entry already has a draft or a logged record.")


def propose(
    db: Session, user_id: uuid.UUID, request_key: uuid.UUID, payload: dict, now: datetime
) -> HealthAction:
    payload = _payload(payload)
    query = select(HealthAction).where(
        HealthAction.user_id == user_id, HealthAction.request_key == str(request_key)
    )
    existing = db.scalar(query)
    if existing is not None:
        # Reusing a request key never silently changes what the person is reviewing.
        first = db.scalar(
            select(HealthActionEvent).where(
                HealthActionEvent.action_id == existing.id,
                HealthActionEvent.user_id == user_id,
                HealthActionEvent.event == "proposed",
            )
        )
        if first is None or _given(first.payload) != _given(payload):
            raise ApiError(
                409, "request_conflict", "This request key belongs to another log payload."
            )
        return existing
    fingerprint = _fingerprint(payload)
    _duplicate(db, user_id, fingerprint)
    row = HealthAction(
        user_id=user_id,
        fingerprint=fingerprint,
        request_key=str(request_key),
        kind=payload["kind"],
        payload=payload,
        version=1,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
            _event(db, row, "proposed", now)
            db.flush()
    except IntegrityError:
        # A concurrent retry won the unique key. Re-enter the same comparison, not a new insert.
        if db.scalar(query) is None:
            _duplicate(db, user_id, fingerprint)
            raise
        return propose(db, user_id, request_key, payload, now)
    return row


def _change(
    db: Session, row: HealthAction, version: int, statuses: tuple[str, ...], values: dict
) -> None:
    result = db.execute(
        update(HealthAction)
        .where(
            HealthAction.id == row.id,
            HealthAction.user_id == row.user_id,
            HealthAction.version == version,
            HealthAction.status.in_(statuses),
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise ApiError(
            409, "stale_action", "This draft changed or is no longer available for this action."
        )
    db.refresh(row)


def revise(
    db: Session,
    user_id: uuid.UUID,
    action_id: uuid.UUID,
    version: int,
    payload: dict,
    now: datetime,
) -> HealthAction:
    row = get(db, user_id, action_id)
    payload = _payload(payload)
    if payload["kind"] != row.kind:
        raise ApiError(422, "invalid_log", "Start a new draft to change the log type.")
    fingerprint = _fingerprint(payload)
    _duplicate(db, user_id, fingerprint, excluding=row.id)
    try:
        with db.begin_nested():
            _change(
                db,
                row,
                version,
                ("draft", "failed"),
                dict(
                    payload=payload,
                    fingerprint=fingerprint,
                    version=version + 1,
                    status="draft",
                    error=None,
                    updated_at=now,
                ),
            )
    except IntegrityError:
        raise ApiError(
            409, "duplicate_log", "This entry already has a draft or a logged record."
        ) from None
    _event(db, row, "revised", now)
    db.flush()
    return row


def cancel(
    db: Session, user_id: uuid.UUID, action_id: uuid.UUID, version: int, now: datetime
) -> HealthAction:
    row = get(db, user_id, action_id)
    _change(db, row, version, ("draft", "failed"), dict(status="cancelled", updated_at=now))
    _event(db, row, "cancelled", now)
    db.flush()
    return row


def execute(
    db: Session,
    user_id: uuid.UUID,
    action_id: uuid.UUID,
    version: int,
    writer: Writer,
    now: datetime,
    *,
    undo: bool = False,
) -> HealthAction:
    """Called by authenticated confirmation endpoints only, never exposed as a model tool.

    The claim and reviewed payload snapshot are committed before sending. A crash afterwards
    leaves executing/undoing, which blocks duplicate sends across processes and restarts.
    """
    row = get(db, user_id, action_id)
    completed = "undone" if undo else "succeeded"
    if row.version == version and row.status == completed:
        return row
    status = "undoing" if undo else "executing"
    if undo and not row.provider_name:
        raise ApiError(409, "not_logged", "This draft has no confirmed Google record to undo.")
    # Re-validate the persisted payload, not caller-supplied data, at the execution boundary.
    try:
        payload = LOG.validate_python(row.payload).google_payload()
    except ValidationError:
        raise ApiError(
            422, "invalid_log", "This draft no longer passes the checks. Edit it first."
        ) from None
    _change(
        db,
        row,
        version,
        ("succeeded",) if undo else ("draft",),
        dict(
            status=status,
            pending_operation="delete" if undo else "create",
            error=None,
            updated_at=now,
        ),
    )
    _event(db, row, "undo_confirmed" if undo else "confirmed", now)
    db.commit()
    try:
        outcome = (
            writer.delete(row.kind, row.provider_name) if undo else writer.create(row.kind, payload)
        )
    except Exception:
        # Do not log provider exceptions: they can contain tokens, payloads or response bodies.
        outcome = Outcome("unknown", error="The outcome is unknown. Do not retry this action.")
    final = completed if outcome.status == "succeeded" else outcome.status
    # A rejected undo does not mean the original entry was removed.
    if undo and outcome.status == "failed":
        final = "succeeded"
    values = dict(
        status=final,
        error=outcome.error,
        operation_name=outcome.operation_name,
        updated_at=now,
        pending_operation=None if outcome.status != "unknown" else row.pending_operation,
    )
    if not undo and outcome.provider_name:
        values["provider_name"] = outcome.provider_name
    _change(db, row, version, (status,), values)
    _event(
        db,
        row,
        "undone"
        if undo and final == "undone"
        else f"{row.pending_operation or status}_{outcome.status}",
        now,
    )
    db.commit()
    return row
