"""Shared fixtures: the PostgreSQL-backed test database (Day 1 design.md Decision 12).

There is no SQLite fallback -- native enums, TIMESTAMPTZ, Numeric, functional unique
indexes, and composite-PK cascades behave differently or not at all on SQLite, so a green
SQLite run would prove nothing about the invariants that make the schema safe.

Binding: ``TEST_DATABASE_URL`` (see .env.example; created by docker-compose.yml). When it
is unset every test marked ``db`` is skipped, explicitly. When it is set but unreachable
the tests fail -- an unreachable database is a broken environment, not an opt-out.

Schema: the real Alembic chain is run to ``head`` once per session, so the migration is
re-verified on every suite run rather than once by hand. Each test then runs inside one
outer transaction that is rolled back, so tests never see each other's rows.
"""

import datetime as dt
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from backend.api.deps import SESSION_COOKIE, get_auth_settings
from backend.auth.passwords import hash_password
from backend.auth.tokens import issue_session_token
from backend.core.config import Settings
from backend.db.session import get_db
from backend.main import create_app
from backend.models import User


def _test_database_url() -> str | None:
    # Only the test URL is read from the environment/.env. The developer's DATABASE_URL is
    # irrelevant here and is never substituted for it.
    settings = Settings(database_url="postgresql://unused:unused@unused/unused")
    return settings.test_database_url


def alembic_config(url: str) -> AlembicConfig:
    """An Alembic config bound to ``url`` that leaves the process's logging alone."""
    config = AlembicConfig("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # ConfigParser escaping
    config.attributes["skip_logging_config"] = True
    return config


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``db`` tests when no test database is configured."""
    if _test_database_url() is not None:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set (see docker-compose.yml)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The test database URL, migrated to ``head`` for the session.

    A plain (sync) fixture on purpose: alembic/env.py calls ``asyncio.run()`` itself, which
    would raise inside the running loop an async fixture executes in.
    """
    url = _test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    command.upgrade(alembic_config(url), "head")
    return url


@pytest_asyncio.fixture
async def db_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine in the test's own event loop.

    Function-scoped with ``NullPool`` rather than session-scoped: a pooled connection
    created under one test's loop cannot be reused under the next, and widening the loop
    scope for the whole suite would change every existing async test's behaviour.
    """
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose every write is rolled back when the test ends.

    The session joins an outer transaction on a dedicated connection and turns its own
    ``commit()`` calls into savepoints, so code under test may commit freely while the
    test still leaves no rows behind.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The app over ASGI with ``get_db`` bound to the rolled-back test session.

    ``httpx.AsyncClient`` rather than Starlette's ``TestClient``: the latter drives the app
    on a separate event loop, and a session created here cannot cross into it.
    """
    app = create_app()

    async def _test_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _test_db
    app.dependency_overrides[get_auth_settings] = test_settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# -- accounts ------------------------------------------------------------------------------------

FIXTURE_PASSWORD = "correct horse battery"
# One real argon2id hash for every fixture account: hashing costs 64 MiB of work per call,
# so only the tests that exercise hashing itself pay for it.
FIXTURE_PASSWORD_HASH = hash_password(FIXTURE_PASSWORD)
TEST_SESSION_SECRET = "test-session-secret-" + "0" * 32


def test_settings() -> Settings:
    """Settings for the app under test: a fixed secret, and no developer .env."""
    return Settings(
        database_url="postgresql://unused:unused@unused/unused",
        session_secret=TEST_SESSION_SECRET,
        _env_file=None,
    )


async def make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, hashed_password=FIXTURE_PASSWORD_HASH)
    db.add(user)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await make_user(db_session, "parent@example.com")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """The second identity every authorization test needs."""
    return await make_user(db_session, "someone.else@example.com")


def session_cookie(user: User) -> str:
    return issue_session_token(user.id, TEST_SESSION_SECRET, dt.timedelta(hours=1))


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set(SESSION_COOKIE, session_cookie(user))


@pytest_asyncio.fixture
async def auth_client(api_client: AsyncClient, user: User) -> AsyncClient:
    """``api_client`` signed in as ``user``."""
    sign_in(api_client, user)
    return api_client
