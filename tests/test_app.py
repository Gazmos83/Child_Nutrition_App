"""Application boot, health reporting, and route surface (tasks 6.2, 6.3, 6.4; Day 6)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.deps import get_auth_settings
from backend.core.config import Settings, get_rag_settings, get_settings
from backend.db.session import reset_engine_cache
from backend.main import app, create_app

NO_ENV_FILE = {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"}

# FastAPI mounts these itself; they are not application routes.
FASTAPI_BUILTIN_PATHS = {
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}

# NOTE: FastAPI 0.141 wraps included routers in `_IncludedRouter` entries and no longer
# flattens their children into `app.routes`, so iterating `app.routes` does NOT reveal
# routes added via `include_router`. The OpenAPI schema is the reliable view of the
# documented surface, and it excludes the built-in docs routes above by construction.


@pytest.fixture
def unconfigured_client(monkeypatch) -> TestClient:
    """A client with no DATABASE_URL, and all config/engine caches cleared."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # A developer's real .env would otherwise be picked up and make this test lie.
    monkeypatch.setattr(
        "backend.core.config.Settings.model_config",
        {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"},
    )
    get_settings.cache_clear()
    reset_engine_cache()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()
        reset_engine_cache()


class TestAppBoots:
    """Task 6.2."""

    def test_create_app_configures_logging_once(self) -> None:
        """Day 6 logging: repeated factories do not stack root handlers."""
        import logging

        create_app()
        create_app()
        root = logging.getLogger()
        own = [h for h in root.handlers if getattr(h, "_nutrition_app_handler", False)]
        assert len(own) == 1

    def test_app_is_importable_without_a_database(self) -> None:
        assert app is not None
        assert len(app.routes) > 0

    def test_factory_returns_a_fresh_app(self) -> None:
        assert create_app() is not create_app()


class TestHealthDegradesGracefully:
    """Task 6.3: 200 with no DATABASE_URL set, not a 500."""

    def test_returns_200_when_database_is_unconfigured(
        self, unconfigured_client: TestClient
    ) -> None:
        response = unconfigured_client.get("/health")
        assert response.status_code == 200

    def test_reports_degraded_and_unconfigured(self, unconfigured_client: TestClient) -> None:
        body = unconfigured_client.get("/health").json()
        assert body["status"] == "degraded"
        assert body["database"] == "unconfigured"
        assert body["app_env"] == "unknown"

    def test_reports_unreachable_when_configured_but_absent(self, monkeypatch) -> None:
        # Port 1 is reserved and never listening, so this exercises the connection-failure
        # path rather than the missing-configuration path.
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/nutrition")
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()
        reset_engine_cache()
        try:
            with TestClient(create_app()) as client:
                body = client.get("/health").json()
            assert body["database"] == "unreachable"
            assert body["status"] == "degraded"
            assert body["app_env"] == "test"
        finally:
            get_settings.cache_clear()
            reset_engine_cache()

    def test_response_shape_is_stable(self, unconfigured_client: TestClient) -> None:
        body = unconfigured_client.get("/health").json()
        assert set(body) == {"status", "app_env", "database"}


class TestProductionGuard:
    """Day 7 (production-hardening spec): prod fails at start, dev boots and reports."""

    @pytest.fixture(autouse=True)
    def _isolated_environment(self, monkeypatch):
        for name in ("SESSION_SECRET", "OPENROUTER_API_KEY", "APP_ENV"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.setattr("backend.core.config.Settings.model_config", NO_ENV_FILE)
        monkeypatch.setattr("backend.core.config.RAGSettings.model_config", NO_ENV_FILE)
        get_settings.cache_clear()
        get_rag_settings.cache_clear()
        reset_engine_cache()
        try:
            yield
        finally:
            get_settings.cache_clear()
            get_rag_settings.cache_clear()
            reset_engine_cache()

    def test_prod_without_a_session_secret_does_not_start(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        with pytest.raises(ValidationError) as exc_info:
            create_app()
        assert "SESSION_SECRET" in str(exc_info.value)

    def test_prod_without_a_provider_key_does_not_start(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("SESSION_SECRET", "s" * 32)
        with pytest.raises(RuntimeError) as exc_info:
            create_app()
        assert "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_prod_fully_configured_starts(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("SESSION_SECRET", "s" * 32)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        with TestClient(create_app()) as client:
            assert client.get("/health").json()["app_env"] == "prod"

    def test_dev_without_either_boots_and_answers_health(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_ENV", "dev")
        with TestClient(create_app()) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["app_env"] == "dev"

    def test_settings_seam_is_used_verbatim(self) -> None:
        settings = Settings(database_url="postgresql://u:p@h/db", app_env="test", _env_file=None)
        with TestClient(create_app(settings=settings)) as client:
            assert client.get("/health").status_code == 200


class TestCors:
    """Day 7 (production-hardening spec): cross-origin access is an explicit allowlist."""

    ORIGIN = "https://app.example"
    PREFLIGHT = {
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    @staticmethod
    def _client(origins: list[str]) -> TestClient:
        settings = Settings(
            database_url="postgresql://u:p@h/db", allowed_origins=origins, _env_file=None
        )
        return TestClient(create_app(settings=settings))

    def test_allowed_origin_is_granted_with_credentials_and_a_request_id(self) -> None:
        with self._client([self.ORIGIN]) as client:
            preflight = client.options("/api/chat", headers=self.PREFLIGHT)
            actual = client.get("/api/foods", headers={"Origin": self.ORIGIN})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == self.ORIGIN
        assert preflight.headers["access-control-allow-credentials"] == "true"
        assert "x-request-id" in preflight.headers
        assert actual.headers["access-control-allow-origin"] == self.ORIGIN

    def test_unknown_origin_is_granted_nothing(self) -> None:
        with self._client([self.ORIGIN]) as client:
            headers = {**self.PREFLIGHT, "Origin": "https://evil.example"}
            preflight = client.options("/api/chat", headers=headers)
            actual = client.get("/api/foods", headers={"Origin": "https://evil.example"})
        # No allow-origin is the denial a browser acts on; Starlette also answers 400.
        assert preflight.status_code == 400
        assert "access-control-allow-origin" not in preflight.headers
        assert "access-control-allow-origin" not in actual.headers

    def test_default_allowlist_grants_no_origin(self) -> None:
        with self._client([]) as client:
            preflight = client.options("/api/chat", headers=self.PREFLIGHT)
        assert "access-control-allow-origin" not in preflight.headers

    def test_request_without_origin_is_unchanged(self) -> None:
        with self._client([self.ORIGIN]) as client:
            response = client.get("/api/foods")
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers


PUBLIC_PATHS = {
    "/health",
    "/api/foods",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
}
# `/api/ask` reads no user data but has required a session since Day 7 (it spends model
# credit), so it belongs here: the loop below asserts the 401.
USER_SCOPED_PATHS = {
    "/api/ask",
    "/api/auth/me",
    "/api/chat",
    "/api/children",
    "/api/children/{child_id}",
    "/api/children/{child_id}/feedings",
    "/api/children/{child_id}/feedings/{feeding_id}",
    "/api/children/{child_id}/targets",
}


class TestRouteSurface:
    """Day 1 task 6.4 inverted on Day 6 (hard rule 9): every user-scoped route exists and
    refuses an unauthenticated request; nothing user-scoped is reachable any other way."""

    def test_documented_surface_is_exactly_public_plus_user_scoped(self) -> None:
        assert set(app.openapi()["paths"]) == PUBLIC_PATHS | USER_SCOPED_PATHS

    def test_only_builtin_docs_routes_are_top_level(self) -> None:
        top_level = {r.path for r in app.routes if getattr(r, "path", None) is not None}
        assert top_level == FASTAPI_BUILTIN_PATHS

    def test_every_user_scoped_operation_refuses_without_a_session(self) -> None:
        """Iterate the OpenAPI schema so the *next* route added without auth fails here."""
        secret_app = create_app()
        secret_app.dependency_overrides[get_auth_settings] = lambda: Settings(
            database_url="postgresql://u:p@h/db", session_secret="s" * 32, _env_file=None
        )
        sample_id = "0198f0a0-0000-7000-8000-000000000001"
        with TestClient(secret_app) as client:
            for path, operations in app.openapi()["paths"].items():
                if path not in USER_SCOPED_PATHS:
                    continue
                concrete = path.replace("{child_id}", sample_id).replace("{feeding_id}", sample_id)
                for method in operations:
                    response = client.request(method.upper(), concrete, json={})
                    assert response.status_code == 401, (method, path, response.status_code)
                    assert response.json() == {"detail": "Sign in to continue"}

    def test_authenticated_routes_report_503_without_a_session_secret(self, monkeypatch) -> None:
        """A missing SESSION_SECRET is loud, not an open door."""
        monkeypatch.delenv("SESSION_SECRET", raising=False)
        monkeypatch.setattr(
            "backend.core.config.Settings.model_config",
            {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"},
        )
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        get_settings.cache_clear()
        try:
            with TestClient(create_app()) as client:
                response = client.get("/api/auth/me")
        finally:
            get_settings.cache_clear()
        assert response.status_code == 503 and "SESSION_SECRET" in response.json()["detail"]

    @pytest.mark.parametrize("path", ["/api/users", "/api/child-profiles", "/api/me", "/children"])
    def test_unknown_paths_are_not_routed(self, path: str) -> None:
        with TestClient(app) as client:
            assert client.get(path).status_code == 404
