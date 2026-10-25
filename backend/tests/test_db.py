import uuid
from datetime import date

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.daily import load_daily, save_daily
from app.db.models import DailyMetric, SyncRun, User

ALEMBIC_INI = "alembic.ini"  # tests run from backend/


@pytest.fixture
def engine(tmp_path):
    """A fresh SQLite database built by running the migrations, not by create_all."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return create_engine(url)


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


def user(session: Session, email: str = "person@example.com") -> uuid.UUID:
    person = User(email=email)
    session.add(person)
    session.flush()
    return person.id


def frame(values: dict[str, list], start: str = "2026-07-01") -> pd.DataFrame:
    days = pd.date_range(start, periods=len(next(iter(values.values()))), name="date")
    return pd.DataFrame(values, index=days)


def test_migrations_match_the_models(engine):
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", str(engine.url))
    command.check(config)  # raises if the models changed without a migration


def test_migrations_can_be_rolled_back(engine):
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", str(engine.url))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_daily_table_round_trips_without_empty_cells(session):
    person = user(session)
    table = frame({"steps": [8000.0, None, 9500.0], "hrv_ms": [45.0, 47.5, None]})
    assert save_daily(session, person, "google_health", table) == 3
    stored = load_daily(session, person, "google_health")
    expected = table[["hrv_ms", "steps"]]
    pd.testing.assert_frame_equal(stored, expected, check_freq=False, check_index_type=False)
    assert session.scalar(select(DailyMetric).where(DailyMetric.value.is_(None))) is None


def test_saving_a_day_again_replaces_it_whole(session):
    person = user(session)
    save_daily(
        session, person, "google_health", frame({"steps": [1000.0], "sleep_minutes": [400.0]})
    )
    save_daily(
        session, person, "google_health", frame({"steps": [1200.0], "sleep_minutes": [None]})
    )
    stored = load_daily(session, person, "google_health")
    assert stored.loc["2026-07-01", "steps"] == 1200
    assert "sleep_minutes" not in stored.columns  # rescored away: not kept from the first sync


def test_sources_are_never_mixed(session):
    person = user(session)
    save_daily(session, person, "takeout", frame({"sleep_minutes": [460.0]}))
    save_daily(session, person, "google_health", frame({"sleep_minutes": [420.0]}))
    assert load_daily(session, person, "takeout").iloc[0]["sleep_minutes"] == 460
    assert load_daily(session, person, "google_health").iloc[0]["sleep_minutes"] == 420


def test_each_user_only_sees_their_own_days(session):
    first, second = user(session, "a@example.com"), user(session, "b@example.com")
    save_daily(session, first, "google_health", frame({"steps": [5000.0]}))
    assert load_daily(session, second, "google_health").empty


def test_date_range_is_start_inclusive_end_exclusive(session):
    person = user(session)
    save_daily(session, person, "google_health", frame({"steps": [1.0, 2.0, 3.0]}))
    stored = load_daily(session, person, "google_health", date(2026, 7, 2), date(2026, 7, 3))
    assert list(stored["steps"]) == [2.0]


def test_unknown_sources_are_rejected(session):
    person = user(session)
    with pytest.raises(ValueError, match="Unknown source"):
        save_daily(session, person, "somewhere", frame({"steps": [1.0]}))
    session.add(
        SyncRun(
            user_id=person,
            source="somewhere",
            range_start=date(2026, 7, 1),
            range_end=date(2026, 7, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_emails_are_unique(session):
    user(session, "same@example.com")
    with pytest.raises(IntegrityError):
        user(session, "same@example.com")


def test_existing_messages_become_each_persons_first_conversation(tmp_path):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    url = f"sqlite:///{tmp_path / 'chats.db'}"
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0006")
    engine = create_engine(url)
    first, second, quiet = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    start = datetime(2026, 10, 1, tzinfo=UTC)
    with engine.begin() as connection:
        for person in (first, second, quiet):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, status, created_at) "
                    "VALUES (:id, :email, 'approved', :at)"
                ),
                {"id": person.hex, "email": f"{person.hex}@example.com", "at": start.isoformat()},
            )
        rows = [
            (first, "user", "  How   did I sleep\nthis week?", 0),
            (first, "assistant", "Steady.", 1),
            (first, "user", "And steps?", 2),
            (second, "user", "x" * 100, 0),
        ]
        for person, role, body, minutes in rows:
            connection.execute(
                text(
                    "INSERT INTO chat_messages (id, user_id, role, text, claims, evidence_ids, "
                    "consulted, refused, created_at) VALUES (:id, :user, :role, :text, '[]', "
                    "'[]', '[]', 0, :at)"
                ),
                {
                    "id": uuid.uuid4().hex,
                    "user": person.hex,
                    "role": role,
                    "text": body,
                    "at": (start + timedelta(minutes=minutes)).isoformat(),
                },
            )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        titles = dict(connection.execute(text("SELECT user_id, title FROM conversations")).all())
        unfiled = connection.execute(
            text("SELECT count(*) FROM chat_messages WHERE conversation_id IS NULL")
        ).scalar()
    assert len(titles) == 2 and unfiled == 0  # no conversation for someone who never asked
    assert sorted(titles.values()) == sorted(["How did I sleep this week?", "x" * 59 + "…"])
    command.downgrade(config, "0006")
