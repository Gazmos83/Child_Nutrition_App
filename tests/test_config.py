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


class TestTestDatabaseUrl:
    """Day 6: the test database is an explicit, optional, separately-validated setting."""

    DEV = "postgresql+asyncpg://u:p@h/nutrition"

    def test_absent_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        assert Settings(database_url=self.DEV, _env_file=None).test_database_url is None

    def test_normalized_like_database_url(self) -> None:
        settings = Settings(
            database_url=self.DEV,
            test_database_url="postgresql://u:p@h/nutrition_test",
            _env_file=None,
        )
        assert settings.test_database_url == "postgresql+asyncpg://u:p@h/nutrition_test"

    def test_non_postgres_test_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, test_database_url="sqlite:///t.db", _env_file=None)


class TestSessionSettings:
    DEV = "postgresql+asyncpg://u:p@h/nutrition"

    def test_blank_secret_is_absent_not_an_error(self) -> None:
        """.env.example ships `SESSION_SECRET=`; the app must still boot."""
        settings = Settings(database_url=self.DEV, session_secret="", _env_file=None)
        assert settings.session_secret is None
        blank_test_url = Settings(database_url=self.DEV, test_database_url="  ", _env_file=None)
        assert blank_test_url.test_database_url is None

    def test_short_secret_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, session_secret="short", _env_file=None)

    def test_ttl_default_and_bounds(self) -> None:
        assert Settings(database_url=self.DEV, _env_file=None).session_ttl_hours == 24 * 7
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, session_ttl_hours=0, _env_file=None)


class TestLoggingSettings:
    DEV = "postgresql+asyncpg://u:p@h/nutrition"

    def test_defaults(self, monkeypatch) -> None:
        for name in ("LOG_FORMAT", "LOG_LEVEL", "AUDIT_LOG_PATH"):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(database_url=self.DEV, _env_file=None)
        assert settings.log_format == "json"
        assert settings.log_level == "INFO"
        assert settings.audit_log_path is None

    def test_level_is_normalised_and_validated(self) -> None:
        settings = Settings(database_url=self.DEV, log_level=" warning ", _env_file=None)
        assert settings.log_level == "WARNING"
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, log_level="LOUD", _env_file=None)

    def test_unknown_format_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, log_format="xml", _env_file=None)

    def test_blank_audit_path_is_absent(self) -> None:
        settings = Settings(database_url=self.DEV, audit_log_path="  ", _env_file=None)
        assert settings.audit_log_path is None


class TestProductionHardeningSettings:
    """Day 7: origins, rate limits, and the production guard (production-hardening spec)."""

    DEV = "postgresql+asyncpg://u:p@h/nutrition"
    ENV = ("ALLOWED_ORIGINS", "RATE_LIMIT_MODEL_PER_MINUTE", "RATE_LIMIT_AUTH_PER_MINUTE")

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch) -> None:
        for name in (*self.ENV, "APP_ENV", "SESSION_SECRET"):
            monkeypatch.delenv(name, raising=False)

    def test_defaults(self) -> None:
        settings = Settings(database_url=self.DEV, _env_file=None)
        assert settings.allowed_origins == []
        assert settings.rate_limit_model_per_minute == 30
        assert settings.rate_limit_auth_per_minute == 10

    @pytest.mark.parametrize("raw", ["", "   ", ","])
    def test_blank_origins_are_an_empty_list(self, raw: str) -> None:
        settings = Settings(database_url=self.DEV, allowed_origins=raw, _env_file=None)
        assert settings.allowed_origins == []

    def test_comma_separated_origins_are_split_and_stripped(self, monkeypatch) -> None:
        monkeypatch.setenv("ALLOWED_ORIGINS", " https://app.example , http://localhost:3000 ")
        settings = Settings(database_url=self.DEV, _env_file=None)
        assert settings.allowed_origins == ["https://app.example", "http://localhost:3000"]

    def test_wildcard_origin_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Settings(database_url=self.DEV, allowed_origins="*", _env_file=None)
        assert "explicitly" in str(exc_info.value)

    def test_negative_limit_is_rejected_and_zero_allowed(self) -> None:
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, rate_limit_model_per_minute=-1, _env_file=None)
        zero = Settings(database_url=self.DEV, rate_limit_auth_per_minute=0, _env_file=None)
        assert zero.rate_limit_auth_per_minute == 0

    def test_prod_without_a_secret_refuses_to_construct(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Settings(database_url=self.DEV, app_env="prod", _env_file=None)
        assert "SESSION_SECRET" in str(exc_info.value)
        with pytest.raises(ValidationError):
            Settings(database_url=self.DEV, app_env="prod", session_secret="", _env_file=None)

    def test_prod_with_a_secret_constructs(self) -> None:
        settings = Settings(
            database_url=self.DEV, app_env="prod", session_secret="s" * 32, _env_file=None
        )
        assert settings.app_env == "prod"

    def test_dev_without_a_secret_still_constructs(self) -> None:
        assert Settings(database_url=self.DEV, app_env="dev", _env_file=None).session_secret is None


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


class TestRAGSettings:
    """Day 3 task 1.2 / design.md Decision 11: RAG configuration is independent of the
    application database and always constructs."""

    RAG_ENV = (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "EMBEDDING_MODEL",
        "MILVUS_DB_PATH",
        "CORPUS_DIR",
        "RAG_MIN_SIMILARITY",
        "RAG_CONTEXT_CHAR_BUDGET",
    )

    @pytest.fixture(autouse=True)
    def _clear_rag_env(self, monkeypatch) -> None:
        for name in self.RAG_ENV:
            monkeypatch.delenv(name, raising=False)

    def test_defaults(self) -> None:
        from backend.core.config import RAGSettings

        settings = RAGSettings(_env_file=None)
        assert settings.openrouter_api_key is None
        assert settings.openrouter_model == "openai/gpt-4o-mini"
        assert settings.embedding_model == "openai/text-embedding-3-small"
        assert settings.milvus_db_path == "milvus.db"
        assert settings.corpus_dir == "knowledge-base"
        assert settings.rag_min_similarity == pytest.approx(0.45)
        assert settings.rag_context_char_budget == 6000

    def test_blank_key_is_treated_as_absent(self) -> None:
        from backend.core.config import RAGSettings

        assert RAGSettings(openrouter_api_key="   ", _env_file=None).openrouter_api_key is None
        assert RAGSettings(openrouter_api_key=" k ", _env_file=None).openrouter_api_key == "k"

    def test_env_overrides(self, monkeypatch) -> None:
        from backend.core.config import RAGSettings

        monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")
        monkeypatch.setenv("RAG_MIN_SIMILARITY", "0.42")
        settings = RAGSettings(_env_file=None)
        assert settings.openrouter_model == "openai/gpt-4.1-mini"
        assert settings.rag_min_similarity == pytest.approx(0.42)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("rag_min_similarity", 1.5), ("rag_min_similarity", -2), ("rag_context_char_budget", 10)],
    )
    def test_out_of_range_values_are_rejected(self, field: str, value) -> None:
        from backend.core.config import RAGSettings

        with pytest.raises(ValidationError):
            RAGSettings(_env_file=None, **{field: value})

    def test_constructs_without_database_url(self, monkeypatch) -> None:
        """The whole point of a second settings class."""
        from backend.core.config import RAGSettings, get_rag_settings

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(
            "backend.core.config.RAGSettings.model_config",
            {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"},
        )
        get_rag_settings.cache_clear()
        try:
            settings = get_rag_settings()
            assert isinstance(settings, RAGSettings)
            assert get_rag_settings() is settings
        finally:
            get_rag_settings.cache_clear()


class TestAdminEmails:
    """food-table-admin: the role is a comma-separated setting, compared case-insensitively."""

    def test_absent_by_default(self, monkeypatch) -> None:
        for name in ("ADMIN_EMAILS", "RATE_LIMIT_ADMIN_PER_MINUTE"):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(database_url="postgresql://u:p@h/db", _env_file=None)
        assert settings.admin_emails == []
        assert settings.rate_limit_admin_per_minute == 30

    def test_split_stripped_lower_cased_and_blanks_dropped(self) -> None:
        settings = Settings(
            database_url="postgresql://u:p@h/db",
            admin_emails=" Parent@Example.com , , other@example.com ",
            _env_file=None,
        )
        assert settings.admin_emails == ["parent@example.com", "other@example.com"]

    def test_blank_means_none(self) -> None:
        settings = Settings(database_url="postgresql://u:p@h/db", admin_emails="", _env_file=None)
        assert settings.admin_emails == []
