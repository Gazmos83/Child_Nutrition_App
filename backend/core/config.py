"""Application configuration, read from the environment.

Settings are resolved lazily via :func:`get_settings` rather than at import time.
That matters for two reasons:

- ``backend.main`` must be importable without a database configured, so the app can
  boot and report an unhealthy database instead of crashing on startup.
- Tests need to construct ``Settings`` with explicit values, without a developer's
  local ``.env`` leaking in.

Two settings classes live here on purpose (Day 3 design.md Decision 11). ``Settings``
requires ``DATABASE_URL`` because the application database is mandatory. ``RAGSettings``
requires nothing: the RAG pipeline, its tests, and the ingestion script never touch
PostgreSQL, and the app must boot -- and ``/health`` must answer -- with no LLM or vector
store configured at all.
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

# OpenRouter's OpenAI-compatible endpoint. Both the chat model and the embedding model go
# through it (CLAUDE.md: never call OpenAI directly with a raw key).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
    # Optional: only the test suite reads it (tests/conftest.py). A separate setting
    # rather than a name derived from DATABASE_URL, so the fixtures that create and drop
    # the schema can never be pointed at development data by accident.
    test_database_url: str | None = Field(
        default=None,
        description="PostgreSQL URL of the database the test suite may create and drop.",
    )
    app_env: Literal["dev", "test", "prod"] = Field(
        default="dev",
        description="Deployment environment.",
    )
    # Day 6 authentication. Optional at construction so the app still boots and /health
    # still answers without it; the auth dependency fails with a 503 naming it instead.
    session_secret: str | None = Field(
        default=None,
        min_length=32,
        description="Secret that signs session tokens. At least 32 characters.",
    )
    session_ttl_hours: int = Field(
        default=24 * 7,
        ge=1,
        le=24 * 30,
        description="How long a signed-in session stays valid.",
    )

    @field_validator("session_secret", "test_database_url", mode="before")
    @classmethod
    def _blank_optional_is_absent(cls, value: object) -> object:
        """``SESSION_SECRET=`` (present but empty, as .env.example ships) means unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _require_asyncpg_scheme(cls, value: str | None) -> str | None:
        """Normalize the URL scheme to asyncpg, or fail with an actionable message."""
        if value is None:
            return None
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


class RAGSettings(BaseSettings):
    """Settings for the knowledge base, embeddings, and the RAG pipeline.

    Every field has a default or is optional, so this always constructs. Code that needs
    the provider checks ``openrouter_api_key`` and fails with a message naming it.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key. Required to embed, ingest, or answer questions.",
    )
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        description="OpenRouter model id used for query translation and answer generation.",
    )
    embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        description=(
            "OpenRouter embedding model id. Ingestion and search must use the same model; "
            "the collection records which one built it."
        ),
    )
    milvus_db_path: str = Field(
        default="milvus.db",
        description="Path to the Milvus Lite database file.",
    )
    corpus_dir: str = Field(
        default="knowledge-base",
        description="Directory holding the Markdown corpus and manifest.yaml.",
    )
    rag_min_similarity: float = Field(
        default=0.45,
        ge=-1.0,
        le=1.0,
        description=(
            "Cosine-similarity floor. Passages below it are dropped; if none remain the "
            "pipeline returns the no-answer message without calling the model."
        ),
    )
    rag_context_char_budget: int = Field(
        default=6000,
        ge=500,
        description="Maximum characters of retrieved context placed in the answer prompt.",
    )

    @field_validator("openrouter_api_key")
    @classmethod
    def _blank_key_is_absent(cls, value: str | None) -> str | None:
        """Treat ``OPENROUTER_API_KEY=`` (present but empty) the same as unset."""
        if value is None:
            return None
        value = value.strip()
        return value or None


@lru_cache(maxsize=1)
def get_rag_settings() -> RAGSettings:
    """Return the process-wide RAG settings, constructing them on first use.

    Never raises for missing configuration: every field is optional or defaulted.
    """
    return RAGSettings()
