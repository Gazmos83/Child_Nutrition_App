"""FastAPI application factory."""

import logging

from fastapi import FastAPI

from backend.api.health import router as health_router
from backend.api.router import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

DESCRIPTION = (
    "Child nutrition assistant for newborns through ~4 years.\n\n"
    "**Not a medical device.** Recommendations are not medical advice; consult a "
    "pediatrician."
)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Child Nutrition AI App",
        description=DESCRIPTION,
        version="0.1.0",
    )

    # Unprefixed: infrastructure probes should not have to track an API version.
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
