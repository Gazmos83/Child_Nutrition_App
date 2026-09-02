"""The Alembic chain round-trips (Day 1 tasks 7.2, 7.3).

``downgrade base`` then ``upgrade head`` must leave nothing behind and fail on nothing:
``op.drop_table`` does not drop PostgreSQL enum types, so a hand-written ``downgrade()``
is the only reason the second ``upgrade`` does not fail on ``CREATE TYPE``.
"""

import asyncio
import datetime as dt
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from tests.conftest import alembic_config

pytestmark = pytest.mark.db

ENUM_TYPES = {"sex", "diet_preference", "allergen", "feeding_type", "activity_level"}
TABLES = {
    "users",
    "child_profiles",
    "child_allergies",
    "feedings",
    "growth_measurements",
    "alembic_version",
}
INITIAL_REVISION = "a1d6f0c0b001"


def test_downgrade_base_then_upgrade_head_round_trips(test_database_url: str) -> None:
    config = alembic_config(test_database_url)

    command.downgrade(config, "base")
    # Alembic keeps its own bookkeeping table; everything of ours must be gone.
    assert _tables(test_database_url) == {"alembic_version"}
    assert _enum_types(test_database_url) == set()

    command.upgrade(config, "head")
    assert _tables(test_database_url) == TABLES
    assert _enum_types(test_database_url) == ENUM_TYPES


def test_enum_labels_match_the_python_vocabularies(test_database_url: str) -> None:
    from backend.models.enums import ActivityLevel, Allergen, DietPreference, FeedingType, Sex

    labels = _enum_labels(test_database_url)
    for name, enum in {
        "sex": Sex,
        "diet_preference": DietPreference,
        "allergen": Allergen,
        "feeding_type": FeedingType,
        "activity_level": ActivityLevel,
    }.items():
        assert labels[name] == [member.value for member in enum], name


def test_upgrade_backfills_birth_date_from_age_in_months(test_database_url: str) -> None:
    """growth-tracking design Decision 8: a profile created at 8 months gets the youngest
    birth date consistent with that -- its creation date minus eight calendar months."""
    config = alembic_config(test_database_url)
    user_id, child_id = uuid.uuid7(), uuid.uuid7()
    created_at = dt.datetime(2026, 8, 31, 22, 30, tzinfo=dt.UTC)

    def seed(conn) -> None:
        conn.execute(
            text("INSERT INTO users (id, email, hashed_password) VALUES (:id, :email, 'x')"),
            {"id": user_id, "email": f"migrate-{user_id}@example.com"},
        )
        conn.execute(
            text(
                "INSERT INTO child_profiles "
                "(id, user_id, age_in_months, weight_kg, sex, created_at) "
                "VALUES (:id, :user_id, 8, 8.5, 'female', :created_at)"
            ),
            {"id": child_id, "user_id": user_id, "created_at": created_at},
        )
        conn.commit()

    def cleanup(conn) -> None:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        conn.commit()

    command.downgrade(config, INITIAL_REVISION)
    _run(test_database_url, seed)
    try:
        command.upgrade(config, "head")
        birth_date = _run(
            test_database_url,
            lambda conn: conn.execute(
                text("SELECT birth_date FROM child_profiles WHERE id = :id"), {"id": child_id}
            ).scalar_one(),
        )
        assert birth_date == dt.date(2025, 12, 31)
        measurements = _run(
            test_database_url,
            lambda conn: conn.execute(
                text("SELECT count(*) FROM growth_measurements")
            ).scalar_one(),
        )
        assert measurements == 0
    finally:
        command.upgrade(config, "head")
        _run(test_database_url, cleanup)


def _run(url: str, fn):
    """Inspect through a short-lived async engine: asyncpg is the only driver installed."""

    async def go():
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _tables(url: str) -> set[str]:
    return set(_run(url, lambda conn: inspect(conn).get_table_names()))


def _enum_types(url: str) -> set[str]:
    return set(_run(url, lambda conn: [e["name"] for e in inspect(conn).get_enums()]))


def _enum_labels(url: str) -> dict[str, list[str]]:
    return _run(url, lambda conn: {e["name"]: e["labels"] for e in inspect(conn).get_enums()})
