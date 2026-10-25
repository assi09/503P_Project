"""The Ask screen's conversation: `GET /chat` and `POST /chat`.

A question is answered by `ask()` with the person's own data, conversation and memory. The request
waits for the answer up to `settings.chat_wait_s`; a slower answer keeps running and is stored when
it is done, so the app finds it when it reloads the chat. One question at a time per person.

Spending: every answer's cost is stored, and a question is refused before any model runs once the
person, or the whole app, has reached its daily cap. The caps count local days.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as WaitTimeout
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actions.schemas import Measured
from app.actions.tools import proposal_tools
from app.agent.ask import ask, default_guard, default_router
from app.agent.context import Attachment, turns_from
from app.agent.experts import EXPERTS, Depth, available
from app.agent.guard import Guard
from app.agent.intent import Intent
from app.agent.llm import LLM, LLMError, OpenAILLM
from app.agent.router import Router
from app.api import schemas
from app.api.auth import Db, approved_user
from app.api.errors import ApiError
from app.api.store import LoadedData, get_data
from app.config import settings
from app.db import chat as store
from app.db import memory
from app.db.models import ChatMessage, User
from app.db.session import session_scope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

HISTORY_SHOWN = 100  # messages the app gets back
HISTORY_USED = 20  # messages the agent sees as context; the context builder trims further
FAILED = "I couldn't finish answering this time. Please try again in a moment."

Sessions = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True)
class AgentParts:
    llm: LLM
    router: Router
    guard: Guard | None


@lru_cache(maxsize=1)
def _agent() -> AgentParts:
    try:
        llm = OpenAILLM.from_settings(settings)
    except LLMError as exc:
        logger.warning("The agent is not available: %s", exc)
        raise ApiError(503, "agent_unavailable", "Answering questions is not set up yet.") from exc
    return AgentParts(llm, default_router(settings), default_guard(settings))


def get_agent() -> AgentParts:
    """FastAPI dependency; tests override it with a scripted model."""
    return _agent()


def get_sessions() -> Sessions:
    """FastAPI dependency: how the answering thread opens its own sessions. Tests override it."""
    return session_scope


# Answers run on their own threads so a request can stop waiting without stopping the answer.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat")
_busy: set[object] = set()
_busy_lock = threading.Lock()


class AttachmentIn(schemas.ApiModel):
    kind: Literal["finding", "metric"]
    id: str | None = Field(default=None, max_length=100)
    metric: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _complete(self):
        if (self.kind == "finding" and not self.id) or (self.kind == "metric" and not self.metric):
            raise ValueError("an attachment needs its id or metric")
        return self


class Question(schemas.ApiModel):
    text: str = Field(min_length=1, max_length=2000)
    expert: Literal["auto", "sleep", "recovery", "activity", "nutrition"] = "auto"
    depth: Literal["quick", "deep"] = "quick"
    attachment: AttachmentIn | None = None


def _message(row: ChatMessage) -> schemas.ChatMessage:
    return schemas.ChatMessage(
        id=str(row.id),
        role=row.role,
        text=row.text,
        evidence_ids=list(row.evidence_ids or []),
        action_ids=list(row.action_ids or []) or None,
        attachment=row.attachment,
        answered_by=row.answered_by if row.role == "assistant" else None,
        routed=row.routed if row.role == "assistant" else None,
        consulted=list(row.consulted or []) or None,
        refused=row.refused or None,
        created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC),
    )


def _day_start(now: datetime) -> datetime:
    """Midnight of the current local day, in UTC."""
    zone = ZoneInfo(settings.timezone)
    local = now.astimezone(zone)
    return datetime.combine(local.date(), time(), zone).astimezone(UTC)


def _spent(db: Session, since: datetime, user: User | None = None) -> float:
    query = select(func.coalesce(func.sum(ChatMessage.cost_usd), 0.0)).where(
        ChatMessage.created_at >= since
    )
    if user is not None:
        query = query.where(ChatMessage.user_id == user.id)
    return float(db.scalar(query))


def check_caps(db: Session, user: User, now: datetime) -> None:
    since = _day_start(now)
    if _spent(db, since) >= settings.chat_daily_cap_total_usd:
        raise ApiError(
            429,
            "app_daily_limit",
            "Patterns has answered all it can for today. Try again tomorrow.",
        )
    if _spent(db, since, user) >= settings.chat_daily_cap_per_user_usd:
        raise ApiError(
            429, "daily_limit", "You've reached today's limit for questions. Try again tomorrow."
        )


def _attachment(data: LoadedData, given: AttachmentIn | None) -> Attachment | None:
    if given is None:
        return None
    if given.kind == "metric":
        if given.metric not in data.daily.frame.columns:
            raise ApiError(422, "invalid_request", "That metric is not in your data.")
        return Attachment(metric=given.metric)
    finding = next((f for f in data.report.findings if f.id == given.id), None)
    if finding is None:
        raise ApiError(404, "not_found", "That finding is no longer in your report.")
    evidence = tuple(data.report.evidence[i] for i in finding.evidence_ids)
    return Attachment(
        metric=finding.metric, finding=f"{finding.title}. {finding.summary}", evidence=evidence
    )


def answer_text(summary: str, claims: list[str], notes: list[str]) -> str:
    """What the person reads: the summary as the answer, then any fixed notes.

    The verified claims back the summary and are shown as evidence links, not repeated as text;
    they are read out only when there is no summary."""
    body = summary.strip() or " ".join(c.strip() for c in claims if c.strip())
    paragraphs: list[str] = []
    for part in (body, *notes):
        part = part.strip()
        if part and part not in paragraphs:
            paragraphs.append(part[0].upper() + part[1:])
    return "\n\n".join(paragraphs) or FAILED


def _answer(
    sessions: Sessions,
    agent: AgentParts,
    user_id,
    question_id,
    data: LoadedData,
    body: Question,
    attachment: Attachment | None,
    now: datetime,
) -> list[ChatMessage]:
    """Runs on a worker thread: answers, stores the answer, and frees the person for the next."""
    try:
        with sessions() as db:
            earlier = [m for m in store.history(db, user_id, HISTORY_USED) if m.id != question_id]
            turns = turns_from(earlier)
            cited = store.load_evidence(db, user_id, {i for t in turns for i in t.evidence_ids})
            remembered = memory.memory_items(db, user_id, now)
        last = earlier[-1] if earlier and earlier[-1].role == "assistant" else None
        continuing_log = None
        if last and last.pending_log_expert:
            created = (
                last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=UTC)
            )
            if timedelta(0) <= now - created <= timedelta(hours=24):
                continuing_log = last.pending_log_expert
        frame = data.daily.frame
        # The agent gets the person's local time, so "just now" or "this morning" needs no
        # question; the data range is in the task separately.
        local_now = now.astimezone(ZoneInfo(settings.timezone))
        question = body.text
        if continuing_log and len(earlier) >= 2 and earlier[-2].role == "user":
            # A reply to the agent's logging question only makes sense with the request it
            # answers, so the agent gets all three, not the bare reply.
            question = (
                f"Earlier request: {earlier[-2].text}\n"
                f"You asked: {earlier[-1].text}\n"
                f"Their reply: {body.text}"
            )
        prepared: list[str] = []

        def measurer(start: datetime, end: datetime) -> Measured:
            # Imported here: the actions routes import Google's, which import this module.
            from app.api.actions import measure_workout

            with sessions() as db:
                return measure_workout(db, user_id, start, end)

        draft_tools = proposal_tools(sessions, user_id, question_id, now, prepared, measurer)
        try:
            reply = ask(
                agent.llm,
                agent.router,
                frame,
                question,
                choice=body.expert,
                depth=Depth(body.depth),
                today=local_now,
                history=turns,
                stored_evidence=cited,
                attachment=attachment,
                guard=agent.guard,
                memory=remembered,
                now=now,
                action_tools=draft_tools,
                continuing_log=continuing_log,
            )
        except Exception:
            logger.exception("Answering failed")
            reply = None
        with sessions() as db:
            question = db.get(ChatMessage, question_id)
            if reply is None:
                answer = store.add_answer(
                    db,
                    user_id,
                    FAILED,
                    claims=[],
                    evidence=[],
                    answered_by=None,
                    routed=None,
                    consulted=[],
                    refused=False,
                    run_id=None,
                )
                return [question, answer]
            result = reply.result
            if prepared:
                note = "A logging draft is ready for review. It has not been sent to Google Health."
                if reply.route.classification.intent == Intent.LOG or any(
                    step.get("continuing_log_expert") for step in result.trace
                ):
                    result.summary, result.claims = note, []
                elif reply.route.expert == "nutrition" and not available(
                    EXPERTS["nutrition"], frame
                ):
                    result.summary = "No nutrition history is available yet. " + note
                else:
                    result.notes.append(note)
            refused = reply.route.action == "refuse"
            memory.mark_used(db, user_id, reply.context.memory_used, now)
            for fact in reply.proposed_facts:
                with suppress(memory.MemoryRejected):
                    memory.propose_fact(db, user_id, **fact, run_id=result.run_id)
            answer = store.add_answer(
                db,
                user_id,
                answer_text(result.summary, [c.text for c in result.claims], result.notes),
                claims=[c.model_dump(mode="json") for c in result.claims],
                evidence=result.evidence.values(),
                answered_by=None if refused else result.expert,
                routed=None if refused else body.expert == "auto",
                consulted=list(result.consulted),
                refused=refused,
                run_id=result.run_id,
                cost_usd=result.budget.cost_usd,
                action_ids=prepared or None,
                pending_log_expert=(reply.route.expert or "general")
                if not prepared
                and (reply.route.expert in draft_tools or reply.route.action == "general")
                and (
                    reply.route.classification.intent == Intent.LOG
                    or (any(step.get("continuing_log_expert") for step in result.trace))
                )
                else None,
            )
            logger.info(
                "Answered run %s: %s, %d claims, $%.4f",
                result.run_id,
                result.stop_reason,
                len(result.claims),
                result.budget.cost_usd,
            )
            return [question, answer]
    finally:
        with _busy_lock:
            _busy.discard(user_id)


@router.get("/chat", response_model=list[schemas.ChatMessage], response_model_exclude_none=True)
def get_chat(db: Db, user: Annotated[User, Depends(approved_user)]) -> list:
    return [_message(m) for m in store.history(db, user.id, HISTORY_SHOWN)]


@router.post("/chat", response_model=list[schemas.ChatMessage], response_model_exclude_none=True)
def post_chat(
    body: Question,
    db: Db,
    user: Annotated[User, Depends(approved_user)],
    data: Annotated[LoadedData, Depends(get_data)],
    agent: Annotated[AgentParts, Depends(get_agent)],
    sessions: Annotated[Sessions, Depends(get_sessions)],
) -> list:
    now = datetime.now(UTC)
    check_caps(db, user, now)
    attachment = _attachment(data, body.attachment)
    with _busy_lock:
        if user.id in _busy:
            raise ApiError(409, "busy", "Still answering your last question.")
        _busy.add(user.id)
    try:
        # Stored before answering, so the question shows even if the answer comes later.
        with sessions() as own:
            question = store.add_question(
                own,
                user.id,
                body.text.strip(),
                body.attachment.model_dump(exclude_none=True) if body.attachment else None,
            )
            question_id = question.id
        future = _pool.submit(
            _answer, sessions, agent, user.id, question_id, data, body, attachment, now
        )
    except BaseException:
        with _busy_lock:
            _busy.discard(user.id)
        raise
    try:
        rows = future.result(timeout=settings.chat_wait_s)
    except WaitTimeout:
        raise ApiError(
            504,
            "still_answering",
            "This is taking longer than usual. The answer will appear here when it is ready.",
        ) from None
    return [_message(row) for row in rows]
