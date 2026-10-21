from contextlib import contextmanager
from datetime import date

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.daily import load_daily
from app.db.models import SyncRun, User
from app.ingest.takeout import DailyData
from app.sync import pull as pull_module
from app.sync.google_auth import ReconnectNeeded
from app.sync.pull import pull

START, END = date(2026, 7, 1), date(2026, 7, 3)


@pytest.fixture
def sessions(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)

    @contextmanager
    def scope():
        with Session(engine, expire_on_commit=False) as session:
            yield session
            session.commit()

    return scope


def fake_load(frame=None, error=None):
    def load(health, start, end):
        if error:
            raise error
        return DailyData(frame=frame, missing=[])

    return load


def test_pull_stores_the_days_and_records_the_run(sessions, monkeypatch):
    days = pd.date_range(START, periods=2, name="date")
    monkeypatch.setattr(
        pull_module, "load_daily", fake_load(pd.DataFrame({"steps": [1.0, 2.0]}, days))
    )
    run = pull(sessions, health=None, email=" Person@Example.com ", start=START, end=END)
    assert run.status == "succeeded" and run.days_written == 2
    with sessions() as session:
        user = session.scalar(select(User))
        assert user.email == "person@example.com"
        assert list(load_daily(session, user.id, "google_health")["steps"]) == [1.0, 2.0]
        stored = session.get(SyncRun, run.id)
        assert stored.finished_at is not None and stored.error is None


def test_a_failed_pull_is_recorded_with_its_reason(sessions, monkeypatch):
    error = ReconnectNeeded("Google sign-in expired; connect again.")
    monkeypatch.setattr(pull_module, "load_daily", fake_load(error=error))
    with pytest.raises(ReconnectNeeded):
        pull(sessions, health=None, email="person@example.com", start=START, end=END)
    with sessions() as session:
        run = session.scalar(select(SyncRun))
        assert run.status == "failed"
        assert run.error == "Google sign-in expired; connect again."
        assert run.days_written is None


def test_pulling_twice_reuses_the_user(sessions, monkeypatch):
    days = pd.date_range(START, periods=1, name="date")
    monkeypatch.setattr(pull_module, "load_daily", fake_load(pd.DataFrame({"steps": [1.0]}, days)))
    pull(sessions, None, "person@example.com", START, END)
    pull(sessions, None, "person@example.com", START, END)
    with sessions() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(SyncRun)).all()) == 2
