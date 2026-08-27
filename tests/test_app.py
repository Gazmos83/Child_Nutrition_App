"""Application boot, health reporting, and route surface (tasks 6.2, 6.3, 6.4)."""

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.db.session import reset_engine_cache
from backend.main import app, create_app

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


class TestNoUserScopedRoutesExposed:
    """Task 6.4 / design.md Risk 6: authorization lands on Day 6, so nothing user-scoped
    may be reachable before then."""

    def test_documented_surface_is_health_ask_and_chat(self) -> None:
        # Day 3 adds /api/ask and Day 5 adds /api/chat; both are deliberately not
        # user-scoped (ask-api and chat-api specs): child details travel in the body.
        assert set(app.openapi()["paths"]) == {"/health", "/api/ask", "/api/chat"}

    def test_only_builtin_docs_routes_are_top_level(self) -> None:
        top_level = {r.path for r in app.routes if getattr(r, "path", None) is not None}
        assert top_level == FASTAPI_BUILTIN_PATHS

    @pytest.mark.parametrize(
        "path",
        ["/api/children", "/api/users", "/api/child-profiles", "/api/me", "/children"],
    )
    def test_user_scoped_paths_are_not_routed(self, path: str) -> None:
        with TestClient(app) as client:
            assert client.get(path).status_code == 404

    def test_api_router_exposes_only_ask_and_chat(self) -> None:
        from backend.api.router import api_router

        assert api_router.prefix == "/api"
        api_paths = {p for p in app.openapi()["paths"] if p.startswith("/api/")}
        assert api_paths == {"/api/ask", "/api/chat"}
