"""Async engine and session management.

The engine is created on first use rather than at import time. ``backend.main`` must be
importable with no database configured so the application can boot and *report* an
unhealthy database instead of crashing before it can serve ``/health``.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call.

    Raises:
        pydantic.ValidationError: if DATABASE_URL is missing or malformed.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        # Verify a pooled connection before handing it out. Managed Postgres providers
        # drop idle connections, and design.md Decision 11 puts one behind every
        # deployment, so the alternative is intermittent errors on the first query.
        pool_pre_ping=True,
        # Never echo SQL: bound parameters would put emails and password hashes into the
        # log (observability spec, "Some things are never logged"). For query debugging
        # raise `sqlalchemy.engine` to DEBUG deliberately and locally.
        echo=False,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        # Attributes stay readable after commit, so a route can serialize the object it
        # just wrote without triggering a lazy reload against a closed session.
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a session, rolling back on error.

    Commit is the caller's responsibility: the request handler knows what constitutes a
    complete unit of work, this dependency does not.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def reset_engine_cache() -> None:
    """Clear the cached engine and session factory.

    For tests that need to rebind to a different database. Not used in production code.
    """
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
