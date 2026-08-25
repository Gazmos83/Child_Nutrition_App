"""Health endpoint.

Deliberately reports dependency failure rather than raising it. A liveness probe that
500s when the database is down cannot distinguish "the app is broken" from "the app is up
and its database is not", and the whole point of the endpoint is to tell them apart.
"""

import logging

from fastapi import APIRouter
from pydantic import ValidationError
from sqlalchemy import text

from backend.core.config import get_settings
from backend.db.session import get_engine
from backend.schemas.health import DatabaseStatus, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _database_status() -> DatabaseStatus:
    """Probe the database, mapping every failure to a status rather than an exception."""
    try:
        engine = get_engine()
    except ValidationError:
        # DATABASE_URL absent or malformed -- a configuration problem, not an outage.
        logger.warning("Database is not configured; reporting 'unconfigured'.")
        return "unconfigured"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # Broad by intent: DNS failure, refused connection, auth rejection, timeout and
        # driver errors are all just "unreachable" to a caller of this endpoint.
        logger.warning("Database probe failed; reporting 'unreachable'.", exc_info=True)
        return "unreachable"

    return "reachable"


@router.get("/health", response_model=HealthResponse, summary="Liveness and dependency status")
async def health() -> HealthResponse:
    """Report application liveness and whether the database is reachable."""
    database = await _database_status()

    try:
        app_env = get_settings().app_env
    except ValidationError:
        app_env = "unknown"

    return HealthResponse(
        status="ok" if database == "reachable" else "degraded",
        app_env=app_env,
        database=database,
    )
