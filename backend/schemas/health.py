"""Response schemas for the health endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

DatabaseStatus = Literal["reachable", "unreachable", "unconfigured"]


class HealthResponse(BaseModel):
    """Liveness and dependency status."""

    status: Literal["ok", "degraded"] = Field(
        description="'ok' when every dependency is reachable, otherwise 'degraded'."
    )
    app_env: str = Field(description="Deployment environment, or 'unknown' if unconfigured.")
    database: DatabaseStatus = Field(
        description=(
            "'reachable' if a trivial query succeeded, 'unconfigured' if DATABASE_URL is "
            "absent or invalid, 'unreachable' if configured but the query failed."
        )
    )
