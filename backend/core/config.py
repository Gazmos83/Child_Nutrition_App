"""Application configuration, read from the environment.

Settings are resolved lazily via :func:`get_settings` rather than at import time.
That matters for two reasons:

- ``backend.main`` must be importable without a database configured, so the app can
  boot and report an unhealthy database instead of crashing on startup.
- Tests need to construct ``Settings`` with explicit values, without a developer's
  local ``.env`` leaking in.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# asyncpg is the only driver this application supports (see design.md Decision 1).
# Provider dashboards hand out bare `postgresql://` URLs, which SQLAlchemy would route
# to the default synchronous driver and fail with an unhelpful error at first query.
_ASYNC_SCHEME = "postgresql+asyncpg"
_NORMALIZABLE_SCHEMES = ("postgresql://", "postgres://")


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description=(
            "PostgreSQL connection URL. A bare postgresql:// scheme is normalized to "
            "postgresql+asyncpg://."
        ),
    )
    app_env: Literal["dev", "test", "prod"] = Field(
        default="dev",
        description="Deployment environment.",
    )

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_scheme(cls, value: str) -> str:
        """Normalize the URL scheme to asyncpg, or fail with an actionable message."""
        url = value.strip()
        if not url:
            raise ValueError("DATABASE_URL must not be empty")

        if url.startswith(f"{_ASYNC_SCHEME}://"):
            return url

        for scheme in _NORMALIZABLE_SCHEMES:
            if url.startswith(scheme):
                return f"{_ASYNC_SCHEME}://{url[len(scheme) :]}"

        scheme = url.split("://", 1)[0] if "://" in url else url
        raise ValueError(
            f"DATABASE_URL must be a PostgreSQL URL using the {_ASYNC_SCHEME} driver, "
            f"got scheme {scheme!r}. This application supports PostgreSQL only "
            "(see design.md Decision 12)."
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, constructing them on first use.

    Raises:
        pydantic.ValidationError: if DATABASE_URL is missing or malformed.
    """
    return Settings()  # type: ignore[call-arg]  # values come from the environment
