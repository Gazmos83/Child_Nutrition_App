"""Settings normalization and failure behaviour (tasks 3.1, 3.2)."""

import pytest
from pydantic import ValidationError

from backend.core.config import Settings

# Every Settings() here passes _env_file=None so a developer's local .env cannot
# leak into the test and mask a failure.


class TestDatabaseUrlNormalization:
    """design.md Risk: a bare postgresql:// URL must not reach SQLAlchemy."""

    @pytest.mark.parametrize(
        "raw",
        [
            "postgresql://user:pw@localhost:5432/nutrition",
            "postgres://user:pw@localhost:5432/nutrition",
        ],
    )
    def test_bare_scheme_is_normalized_to_asyncpg(self, raw: str) -> None:
        settings = Settings(database_url=raw, _env_file=None)
        assert settings.database_url.startswith("postgresql+asyncpg://")
        # The credentials and path survive the rewrite untouched.
        assert settings.database_url.endswith("user:pw@localhost:5432/nutrition")

    def test_asyncpg_scheme_passes_through_unchanged(self) -> None:
        raw = "postgresql+asyncpg://user:pw@localhost:5432/nutrition"
        assert Settings(database_url=raw, _env_file=None).database_url == raw

    def test_surrounding_whitespace_is_stripped(self) -> None:
        settings = Settings(database_url="  postgresql://u:p@h/db  ", _env_file=None)
        assert settings.database_url == "postgresql+asyncpg://u:p@h/db"

    @pytest.mark.parametrize(
        "raw",
        [
            "sqlite+aiosqlite:///./test.db",  # Decision 12: PostgreSQL only
            "mysql://user:pw@localhost/db",
            "not-a-url",
        ],
    )
    def test_non_postgres_url_is_rejected(self, raw: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Settings(database_url=raw, _env_file=None)
        assert "postgresql+asyncpg" in str(exc_info.value)

    def test_empty_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Settings(database_url="   ", _env_file=None)
        assert "must not be empty" in str(exc_info.value)


class TestMissingConfiguration:
    """Task 3.2: absence of DATABASE_URL must fail loudly and name the field."""

    def test_missing_database_url_names_the_field(self, monkeypatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)

        error = str(exc_info.value)
        assert "database_url" in error.lower()
        assert "required" in error.lower()

    def test_unknown_app_env_is_rejected(self, monkeypatch) -> None:
        monkeypatch.delenv("APP_ENV", raising=False)
        with pytest.raises(ValidationError):
            Settings(
                database_url="postgresql://u:p@h/db",
                app_env="staging",
                _env_file=None,
            )


class TestSettingsCaching:
    def test_get_settings_is_cached(self, monkeypatch) -> None:
        from backend.core.config import get_settings

        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        get_settings.cache_clear()
        try:
            assert get_settings() is get_settings()
        finally:
            get_settings.cache_clear()
