"""FastAPI application factory."""

from fastapi import FastAPI
from pydantic import ValidationError

from backend.api.health import router as health_router
from backend.api.middleware import RequestContextMiddleware
from backend.api.router import api_router
from backend.core.config import Settings, get_settings
from backend.core.logging import configure_logging

DESCRIPTION = (
    "Child nutrition assistant for newborns through ~4 years.\n\n"
    "**Not a medical device.** Recommendations are not medical advice; consult a "
    "pediatrician."
)


def _settings_if_configured() -> Settings | None:
    """Settings, or None when DATABASE_URL is absent -- the app still boots (see /health)."""
    try:
        return get_settings()
    except ValidationError:
        return None


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging(_settings_if_configured())

    app = FastAPI(
        title="Child Nutrition AI App",
        description=DESCRIPTION,
        version="0.1.0",
    )
    # Request id, access record with latency, and the last-resort 500 (observability spec).
    app.add_middleware(RequestContextMiddleware)

    # Unprefixed: infrastructure probes should not have to track an API version.
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
