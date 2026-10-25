"""Storing and reading a person's conversations and the evidence their answers cite.

A person has any number of conversations; memory (facts, findings, answers) is the person's and
shared by all of them. A turn is stored only after it is complete: the question, then the answer
with its verified claims and the evidence they cite. Every query filters on the user.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evidence import Evidence
from app.db.models import ChatMessage, Conversation, EvidenceRecord

NEW_TITLE = "New chat"
TITLE_LENGTH = 60


def title_from(question: str) -> str:
    """A conversation's name from its first question: one line, at most TITLE_LENGTH characters."""
    text = " ".join(question.split()) or NEW_TITLE
    return text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1].rstrip() + "…"


def create_conversation(
    session: Session, user_id: uuid.UUID, title: str = NEW_TITLE
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    session.add(conversation)
    session.flush()
    return conversation


def get_conversation(
    session: Session, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    return session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )


def latest_conversation(session: Session, user_id: uuid.UUID) -> Conversation | None:
    return session.scalar(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )


def conversations(session: Session, user_id: uuid.UUID) -> list[tuple[Conversation, int]]:
    """The person's conversations, most recently used first, each with its number of messages."""
    counts = (
        select(ChatMessage.conversation_id, func.count().label("messages"))
        .where(ChatMessage.user_id == user_id)
        .group_by(ChatMessage.conversation_id)
        .subquery()
    )
    rows = session.execute(
        select(Conversation, func.coalesce(counts.c.messages, 0))
        .outerjoin(counts, counts.c.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return [(conversation, count) for conversation, count in rows]


def add_question(
    session: Session,
    user_id: uuid.UUID,
    text: str,
    attachment: dict | None = None,
    conversation: Conversation | None = None,
) -> ChatMessage:
    message = ChatMessage(
        user_id=user_id,
        role="user",
        text=text,
        attachment=attachment,
        conversation_id=conversation.id if conversation else None,
    )
    session.add(message)
    if conversation is not None:
        if conversation.title == NEW_TITLE:
            conversation.title = title_from(text)
        conversation.updated_at = datetime.now(UTC)
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
    action_ids: list[str] | None = None,
    pending_log_expert: str | None = None,
    conversation_id: uuid.UUID | None = None,
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
        action_ids=action_ids,
        pending_log_expert=pending_log_expert,
        conversation_id=conversation_id,
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


def history(
    session: Session,
    user_id: uuid.UUID,
    limit: int | None = None,
    conversation_id: uuid.UUID | None = None,
) -> list[ChatMessage]:
    """A conversation, oldest first (every message without `conversation_id`); with `limit`, only
    the latest messages."""
    query = select(ChatMessage).where(ChatMessage.user_id == user_id)
    if conversation_id is not None:
        query = query.where(ChatMessage.conversation_id == conversation_id)
    query = (
        query
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
