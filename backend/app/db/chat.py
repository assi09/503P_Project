"""Storing and reading a person's conversation and the evidence its answers cite.

One thread per person. A turn is stored only after it is complete: the question, then the answer
with its verified claims and the evidence they cite. Every query filters on the user.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.evidence import Evidence
from app.db.models import ChatMessage, EvidenceRecord


def add_question(
    session: Session, user_id: uuid.UUID, text: str, attachment: dict | None = None
) -> ChatMessage:
    message = ChatMessage(user_id=user_id, role="user", text=text, attachment=attachment)
    session.add(message)
    session.flush()
    return message


def add_answer(
    session: Session,
    user_id: uuid.UUID,
    text: str,
    *,
    claims: list[dict],
    evidence: Iterable[Evidence],
    answered_by: str | None,
    routed: bool | None,
    consulted: list[str],
    refused: bool,
    run_id: str | None,
    cost_usd: float | None = None,
) -> ChatMessage:
    """Stores an answer, its verified claims, and the evidence they cite (once per id)."""
    cited = {i for claim in claims for i in claim.get("evidence_ids", [])}
    store_evidence(session, user_id, run_id, evidence, cited)
    message = ChatMessage(
        user_id=user_id,
        role="assistant",
        text=text,
        claims=claims,
        evidence_ids=sorted(cited),
        answered_by=answered_by,
        routed=routed,
        consulted=consulted,
        refused=refused,
        run_id=run_id,
        cost_usd=cost_usd,
    )
    session.add(message)
    session.flush()
    return message


def store_evidence(
    session: Session,
    user_id: uuid.UUID,
    run_id: str | None,
    evidence: Iterable[Evidence],
    cited: set[str],
) -> None:
    """Stores the cited evidence, once per id; raises `ValueError` if any of it was not given."""
    records = [e for e in evidence if e.id in cited]
    if missing := cited - {e.id for e in records}:
        raise ValueError(f"claims cite evidence that was not given: {', '.join(sorted(missing))}")
    if not records:
        return
    stored = set(
        session.scalars(
            select(EvidenceRecord.id).where(
                EvidenceRecord.user_id == user_id, EvidenceRecord.id.in_(cited)
            )
        )
    )
    session.add_all(
        EvidenceRecord(
            user_id=user_id,
            id=e.id,
            run_id=run_id,
            tool=e.tool,
            payload=e.model_dump(mode="json"),
        )
        for e in records
        if e.id not in stored
    )


def history(session: Session, user_id: uuid.UUID, limit: int | None = None) -> list[ChatMessage]:
    """The conversation, oldest first; with `limit`, only the latest messages."""
    query = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        # Newest first for the limit; on a tie the answer sorts first, so reversed the question
        # comes before its answer.
        .order_by(ChatMessage.created_at.desc(), ChatMessage.role.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return list(reversed(session.scalars(query).all()))


def load_evidence(session: Session, user_id: uuid.UUID, ids: Iterable[str]) -> dict[str, Evidence]:
    """The stored evidence with these ids that belongs to this user; others are left out."""
    wanted = set(ids)
    if not wanted:
        return {}
    rows = session.scalars(
        select(EvidenceRecord).where(
            EvidenceRecord.user_id == user_id, EvidenceRecord.id.in_(wanted)
        )
    )
    return {row.id: Evidence.model_validate(row.payload) for row in rows}
