"""The memory write path: what may be stored, by whom, and for how long (docs/architecture.md).

- **Findings** come only from verified claims of investigation runs; a newer finding on the same
  metric supersedes the older one.
- **Context questions** are written by code from a template and a fixed menu of options; the
  person's answer must be one of them. A metric and period once asked about is not asked again,
  and questions stop for a while after the person dismisses two.
- **Check-ins** are the person's: a rating from 1 to 5 and tags from a fixed list, for today only.
- **Facts** are proposed by the agent and kept only once the person approves; text that reads like
  an instruction is refused, and a fact the person declined is not proposed again.

Every function takes the user, and every query filters on it. Rejected writes raise
`MemoryRejected`, whose message is safe to show.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.agent.present import METRICS, label, short_date
from app.agent.sanitize import clean, reads_like_instruction
from app.analysis.evidence import Evidence
from app.db.chat import store_evidence
from app.db.models import (
    CHECKIN_TAGS,
    CONTEXT_OPTIONS,
    FACT_KINDS,
    CheckIn,
    ContextQuestion,
    Finding,
    MemoryFact,
)

FINDING_KINDS = ("change", "association")
FINDING_DAYS = 90
ANSWER_DAYS = 180
CHECKIN_DAYS = 365
FACT_UNUSED_DAYS = 60  # approved facts unused this long are no longer retrieved
MAX_FACT_CHARS = 120
# After this many dismissals within the window, no new question for a while.
BACKOFF_DISMISSALS, BACKOFF_WINDOW_DAYS, BACKOFF_QUIET_DAYS = 2, 30, 14
DECLINED = "rather_not_say"  # an answer, but counted like a dismissal
PROMPT = "Something changed in your {metric} around {day}. Was anything going on then?"


class MemoryRejected(ValueError):
    """A write the memory rules do not allow; the message is safe to show."""


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes; they are stored in UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# Findings


def save_findings(
    session: Session,
    user_id: uuid.UUID,
    run_id: str,
    claims: Iterable[dict],
    evidence: dict[str, Evidence],
    now: datetime | None = None,
) -> list[Finding]:
    """Stores a run's verified change and association claims as findings, with their evidence."""
    now = now or _now()
    saved: list[Finding] = []
    for claim in claims:
        if claim.get("kind") not in FINDING_KINDS or not claim.get("metric"):
            continue
        ids = list(claim.get("evidence_ids", []))
        if missing := [i for i in ids if i not in evidence]:
            raise MemoryRejected(f"A finding cites evidence that was not given: {missing}.")
        cited = [evidence[i] for i in ids]
        windows = [w for e in cited for w in e.windows]
        effects = [
            abs(v)
            for e in cited
            for v in (e.stats.get("cliffs_delta"), e.stats.get("rho"))
            if isinstance(v, int | float)
        ]
        metric = claim["metric"]
        session.execute(
            update(Finding)
            .where(
                Finding.user_id == user_id,
                Finding.metric == metric,
                Finding.superseded_at.is_(None),
                Finding.run_id != run_id,
            )
            .values(superseded_at=now)
        )
        finding = Finding(
            user_id=user_id,
            run_id=run_id,
            metric=metric,
            kind=claim["kind"],
            direction=claim.get("direction"),
            text=claim["text"],
            evidence_ids=ids,
            window_start=min(w.start for w in windows),
            window_end=max(w.end for w in windows),
            effect=max(effects) if effects else None,
            created_at=now,
        )
        session.add(finding)
        saved.append(finding)
        store_evidence(session, user_id, run_id, cited, set(ids))
    session.flush()
    return saved


def current_findings(
    session: Session, user_id: uuid.UUID, now: datetime | None = None
) -> list[Finding]:
    """Findings not superseded and younger than 90 days, newest first."""
    since = (now or _now()) - timedelta(days=FINDING_DAYS)
    query = (
        select(Finding)
        .where(
            Finding.user_id == user_id,
            Finding.superseded_at.is_(None),
            Finding.created_at >= since,
        )
        .order_by(Finding.created_at.desc())
    )
    return list(session.scalars(query))


# Context questions


def ask_question(
    session: Session,
    user_id: uuid.UUID,
    metric: str,
    start: date,
    end: date,
    *,
    run_id: str | None = None,
    now: datetime | None = None,
) -> ContextQuestion | None:
    """Asks about a change, unless it was asked before or the person has been dismissing them."""
    if metric not in METRICS:
        raise MemoryRejected(f"Unknown metric {metric!r}.")
    now = now or _now()
    earlier = list(
        session.scalars(select(ContextQuestion).where(ContextQuestion.user_id == user_id))
    )
    if any(q.metric == metric and q.window_start <= end and start <= q.window_end for q in earlier):
        return None  # never the same thing twice
    recent = now - timedelta(days=BACKOFF_WINDOW_DAYS)
    declined = [q for q in earlier if _declined(q) and _aware(q.answered_at) >= recent]
    if len(declined) >= BACKOFF_DISMISSALS and now - max(
        _aware(q.answered_at) for q in declined
    ) < timedelta(days=BACKOFF_QUIET_DAYS):
        return None
    question = ContextQuestion(
        user_id=user_id,
        run_id=run_id,
        metric=metric,
        prompt=PROMPT.format(metric=label(metric), day=short_date(start)),
        window_start=start,
        window_end=end,
        options=list(CONTEXT_OPTIONS),
        asked_at=now,
    )
    session.add(question)
    session.flush()
    return question


def _declined(question: ContextQuestion) -> bool:
    return question.answered_at is not None and (
        question.status == "dismissed" or question.answer == DECLINED
    )


def answer_question(
    session: Session,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    answer: str | None,
    now: datetime | None = None,
) -> ContextQuestion:
    """Records the person's choice; None means they skipped the question."""
    question = session.scalar(
        select(ContextQuestion).where(
            ContextQuestion.user_id == user_id, ContextQuestion.id == question_id
        )
    )
    if question is None:
        raise MemoryRejected("There is no such question.")
    if question.status != "asked":
        raise MemoryRejected("This question was already answered.")
    if answer is not None and answer not in question.options:
        raise MemoryRejected(f"Choose one of: {', '.join(question.options)}.")
    question.status = "dismissed" if answer is None else "answered"
    question.answer = answer
    question.answered_at = now or _now()
    session.flush()
    return question


# Check-ins


def save_checkin(
    session: Session,
    user_id: uuid.UUID,
    day: date,
    rating: int,
    tags: Iterable[str] = (),
    *,
    today: date,
) -> CheckIn:
    """Sets or changes today's check-in."""
    if day != today:
        raise MemoryRejected("Only today's check-in can be set or changed.")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise MemoryRejected("The rating is a whole number from 1 to 5.")
    chosen = list(dict.fromkeys(tags))
    if unknown := [t for t in chosen if t not in CHECKIN_TAGS]:
        raise MemoryRejected(f"Unknown tags: {', '.join(unknown)}.")
    checkin = session.get(CheckIn, (user_id, day))
    if checkin is None:
        checkin = CheckIn(user_id=user_id, day=day, rating=rating, tags=chosen)
        session.add(checkin)
    else:
        checkin.rating, checkin.tags = rating, chosen
    session.flush()
    return checkin


def checkins(session: Session, user_id: uuid.UUID, start: date, end: date) -> list[CheckIn]:
    """Check-ins from `start` to `end` inclusive, oldest first."""
    query = (
        select(CheckIn)
        .where(CheckIn.user_id == user_id, CheckIn.day >= start, CheckIn.day <= end)
        .order_by(CheckIn.day)
    )
    return list(session.scalars(query))


# Facts


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def propose_fact(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    text: str,
    metrics: Iterable[str] = (),
    *,
    run_id: str | None = None,
) -> MemoryFact | None:
    """Stores the agent's proposal for the person to approve; None if they declined it before."""
    if kind not in FACT_KINDS:
        raise MemoryRejected(f"A fact is one of: {', '.join(FACT_KINDS)}.")
    cleaned = clean(text, 10 * MAX_FACT_CHARS)
    if not cleaned:
        raise MemoryRejected("A fact needs text.")
    if len(cleaned) > MAX_FACT_CHARS:
        raise MemoryRejected(f"A fact is at most {MAX_FACT_CHARS} characters.")
    if reads_like_instruction(cleaned):
        raise MemoryRejected("This reads like an instruction, so it is not kept as a fact.")
    concerned = list(dict.fromkeys(metrics))
    if unknown := [m for m in concerned if m not in METRICS]:
        raise MemoryRejected(f"Unknown metrics: {', '.join(unknown)}.")
    same = [
        fact
        for fact in session.scalars(select(MemoryFact).where(MemoryFact.user_id == user_id))
        if _normalized(fact.text) == _normalized(cleaned)
    ]
    if any(fact.status == "declined" for fact in same):
        return None  # the person said no; do not ask again
    if same:
        return same[0]
    fact = MemoryFact(
        user_id=user_id, kind=kind, text=cleaned, metrics=concerned, source_run_id=run_id
    )
    session.add(fact)
    session.flush()
    return fact


def decide_fact(
    session: Session,
    user_id: uuid.UUID,
    fact_id: uuid.UUID,
    approve: bool,
    now: datetime | None = None,
) -> MemoryFact:
    fact = _fact(session, user_id, fact_id)
    if fact.status != "proposed":
        raise MemoryRejected("This fact was already decided.")
    fact.status = "approved" if approve else "declined"
    fact.decided_at = now or _now()
    session.flush()
    return fact


def delete_fact(session: Session, user_id: uuid.UUID, fact_id: uuid.UUID) -> None:
    session.delete(_fact(session, user_id, fact_id))
    session.flush()


def _fact(session: Session, user_id: uuid.UUID, fact_id: uuid.UUID) -> MemoryFact:
    fact = session.scalar(
        select(MemoryFact).where(MemoryFact.user_id == user_id, MemoryFact.id == fact_id)
    )
    if fact is None:
        raise MemoryRejected("There is no such fact.")
    return fact


# Lifetimes


def expire(session: Session, user_id: uuid.UUID, now: datetime | None = None) -> dict[str, int]:
    """Deletes what has outlived its lifetime; returns how many rows of each kind went."""
    now = now or _now()
    removed = {}
    for name, table, column, days in (
        ("findings", Finding, Finding.created_at, FINDING_DAYS),
        ("context_questions", ContextQuestion, ContextQuestion.asked_at, ANSWER_DAYS),
    ):
        result = session.execute(
            delete(table).where(table.user_id == user_id, column < now - timedelta(days=days))
        )
        removed[name] = result.rowcount
    cutoff = now.date() - timedelta(days=CHECKIN_DAYS)
    result = session.execute(
        delete(CheckIn).where(CheckIn.user_id == user_id, CheckIn.day < cutoff)
    )
    removed["checkins"] = result.rowcount
    return removed
