"""Database engine and sessions."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@lru_cache(maxsize=1)
def engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


@contextmanager
def session_scope(bind: Engine | None = None) -> Iterator[Session]:
    """A session that commits on success and rolls back on error."""
    session = sessionmaker(bind or engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
