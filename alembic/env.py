"""Alembic environment: async engine, URL from application settings.

The connection URL is never read from ``alembic.ini`` -- it comes from ``DATABASE_URL``
through :func:`backend.core.config.get_settings`, so the migration chain and the
application can only ever disagree about the database if the environment does.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from backend.core.config import get_settings

# Importing the package populates Base.metadata with every model (backend/models/__init__).
from backend.models import Base

config = context.config

# tests/conftest.py drives migrations programmatically and sets both of these: the test
# database URL, and a flag to leave logging alone (alembic.ini's logging section would
# otherwise reconfigure the root logger under the running test suite).
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    # ConfigParser interpolates `%`; a URL-encoded password must be escaped for it.
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (``alembic upgrade head --sql``)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Design.md Decision 1: the migration runner shares the application's asyncpg driver."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
