"""FastAPI application factory."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from backend.api.health import router as health_router
from backend.api.middleware import RequestContextMiddleware
from backend.api.rate_limit import RateLimiter
from backend.api.router import api_router
from backend.core.config import Settings, get_rag_settings, get_settings
from backend.core.logging import configure_logging

DESCRIPTION = (
    "Child nutrition assistant for newborns through ~4 years.\n\n"
    "**Not a medical device.** Recommendations are not medical advice; consult a "
    "pediatrician."
)


def _settings_if_configured(settings: Settings | None = None) -> Settings | None:
    """Settings, or None when DATABASE_URL is absent -- the app still boots (see /health).

    In production the failure propagates instead (production-hardening spec): a deploy
    with a missing or invalid setting must fail, not serve 503s. ``Settings`` did not
    construct, so the environment is read directly here.
    """
    if settings is not None:
        return settings
    try:
        return get_settings()
    except ValidationError:
        if os.environ.get("APP_ENV", "").strip() == "prod":
            raise
        return None


def _require_production_configuration(settings: Settings | None) -> None:
    """Refuse to start a production instance that could not answer a question."""
    if settings is None or settings.app_env != "prod":
        return
    if get_rag_settings().openrouter_api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is required when APP_ENV=prod")


def _rate_limits(settings: Settings | None) -> dict[str, int]:
    """Per-minute limits by bucket; the Settings defaults apply when unconfigured."""
    fields = Settings.model_fields
    return {
        "model": (
            settings.rate_limit_model_per_minute
            if settings is not None
            else fields["rate_limit_model_per_minute"].default
        ),
        "auth": (
            settings.rate_limit_auth_per_minute
            if settings is not None
            else fields["rate_limit_auth_per_minute"].default
        ),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    ``settings`` is a seam for tests; the running application reads the environment.
    """
    settings = _settings_if_configured(settings)
    _require_production_configuration(settings)
    configure_logging(settings)

    app = FastAPI(
        title="Child Nutrition AI App",
        description=DESCRIPTION,
        version="0.1.0",
    )
    # Added first, so it runs *inside* the request-context middleware below and preflight
    # answers carry X-Request-ID and an access record too. An empty allowlist -- the
    # default, since the browser reaches the API through the Next.js same-origin rewrite --
    # emits no CORS headers at all (production-hardening spec).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins if settings is not None else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Request id, access record with latency, and the last-resort 500 (observability spec).
    app.add_middleware(RequestContextMiddleware)
    app.state.rate_limiter = RateLimiter(_rate_limits(settings))

    # Unprefixed: infrastructure probes should not have to track an API version.
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
