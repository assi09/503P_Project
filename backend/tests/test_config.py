"""Settings read from the environment, as a host such as Railway sets them."""

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("given", "used"),
    [
        ("postgresql://u:p@db.internal:5432/app", "postgresql+psycopg://u:p@db.internal:5432/app"),
        ("postgres://u:p@db.internal:5432/app", "postgresql+psycopg://u:p@db.internal:5432/app"),
        ("postgresql+psycopg://u:p@localhost:5433/x", "postgresql+psycopg://u:p@localhost:5433/x"),
        ("sqlite:///local.db", "sqlite:///local.db"),
    ],
)
def test_a_hosted_database_url_gets_the_psycopg_driver(given, used):
    assert Settings(database_url=given).database_url == used


def test_lists_come_from_json_in_the_environment(monkeypatch):
    monkeypatch.setenv("FA_CORS_ORIGINS", '["https://patterns.example.com"]')
    assert Settings().cors_origins == ["https://patterns.example.com"]
