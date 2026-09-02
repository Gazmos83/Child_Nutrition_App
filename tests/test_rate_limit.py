"""Per-client rate limits (Day 7 tasks 2.1, 2.2; production-hardening spec)."""

import logging

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_auth_settings
from backend.api.rate_limit import RateLimiter
from backend.chat import copy
from backend.core.config import Settings
from backend.db.session import get_db
from backend.main import create_app


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestRateLimiter:
    """Task 2.1: the window arithmetic, with an injected clock."""

    def test_admits_n_then_refuses_with_a_positive_wait(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter({"model": 3}, clock=clock)
        assert [limiter.check("model", "1.2.3.4") for _ in range(3)] == [None, None, None]
        clock.now += 10
        wait = limiter.check("model", "1.2.3.4")
        assert wait == 50  # 60-second window, 10 seconds in

    def test_wait_is_at_least_one_second(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter({"model": 1}, clock=clock)
        limiter.check("model", "c")
        clock.now += 59.9
        assert limiter.check("model", "c") == 1

    def test_clients_are_independent(self) -> None:
        limiter = RateLimiter({"model": 1}, clock=FakeClock())
        assert limiter.check("model", "a") is None
        assert limiter.check("model", "a") is not None
        assert limiter.check("model", "b") is None

    def test_buckets_are_independent(self) -> None:
        limiter = RateLimiter({"model": 1, "auth": 1}, clock=FakeClock())
        assert limiter.check("model", "a") is None
        assert limiter.check("auth", "a") is None
        assert limiter.check("model", "a") is not None

    def test_next_window_admits_again(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter({"model": 1}, clock=clock)
        limiter.check("model", "a")
        assert limiter.check("model", "a") is not None
        clock.now += 60
        assert limiter.check("model", "a") is None

    def test_zero_and_unknown_buckets_never_refuse(self) -> None:
        limiter = RateLimiter({"model": 0}, clock=FakeClock())
        assert all(limiter.check("model", "a") is None for _ in range(50))
        assert all(limiter.check("nothing", "a") is None for _ in range(50))

    def test_expired_windows_are_forgotten(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter({"model": 5}, clock=clock)
        for client in ("a", "b", "c"):
            limiter.check("model", client)
        clock.now += 61
        limiter.check("model", "d")
        assert set(limiter._windows) == {("model", "d")}


# -- routes ---------------------------------------------------------------------------------------

TIGHT = Settings(
    database_url="postgresql://u:p@h/db",
    session_secret="s" * 32,
    rate_limit_model_per_minute=2,
    rate_limit_auth_per_minute=2,
    rate_limit_admin_per_minute=2,
    admin_emails="admin@example.com",
    _env_file=None,
)
CREDENTIALS = {"email": "parent@example.com", "password": "correct horse battery"}


async def _no_db():
    """No database in these tests: every limited request is refused or 401s before a query."""
    yield None


def make_client(settings: Settings) -> TestClient:
    app = create_app(settings=settings)
    app.dependency_overrides[get_auth_settings] = lambda: settings
    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    with make_client(TIGHT) as c:
        yield c


def access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "backend.api.access"]


class TestModelRoutes:
    """Task 2.2: /api/ask and /api/chat share the `model` bucket; refusal precedes any work."""

    def test_third_request_is_429_with_headers_and_access_record(self, client, caplog) -> None:
        caplog.set_level(logging.INFO)
        # Unauthenticated on purpose: the limiter must run before the session dependency,
        # so these count and are cheap (401s).
        first, second = (client.post("/api/chat", json={"message": "hi"}) for _ in range(2))
        assert first.status_code == 401 and second.status_code == 401
        third = client.post("/api/chat", json={"message": "hi"})
        assert third.status_code == 429
        assert third.json() == {"detail": copy.RATE_LIMITED}
        assert int(third.headers["retry-after"]) >= 1
        assert "x-request-id" in third.headers
        refused = [r for r in access_records(caplog) if r.status == 429]
        assert len(refused) == 1 and refused[0].route == "/api/chat"

    def test_ask_and_chat_share_the_bucket(self, client) -> None:
        assert client.post("/api/ask", json={"question": "iron?"}).status_code != 429
        assert client.post("/api/chat", json={"message": "hi"}).status_code != 429
        assert client.post("/api/ask", json={"question": "iron?"}).status_code == 429

    def test_foods_is_never_limited(self, client) -> None:
        assert all(client.get("/api/foods").status_code == 200 for _ in range(5))

    def test_client_address_appears_nowhere(self, client, caplog) -> None:
        caplog.set_level(logging.DEBUG)
        for _ in range(3):
            response = client.post("/api/chat", json={"message": "hi"})
        assert response.status_code == 429
        host = client.base_url.host  # "testserver": the peer TestClient reports
        assert "testclient" not in response.text and host not in response.text
        assert all("testclient" not in r.getMessage() for r in caplog.records)
        assert not any(hasattr(r, "client") or hasattr(r, "client_host") for r in caplog.records)


class TestAuthRoutes:
    """Task 2.2: register and login share the `auth` bucket; refusal precedes hashing."""

    def test_third_login_is_429_before_any_password_work(self, client, monkeypatch) -> None:
        verified: list[str] = []

        def spy(hashed, password):
            verified.append(password)
            return False

        monkeypatch.setattr("backend.api.auth.verify_password", spy)
        monkeypatch.setattr("backend.api.auth._user_by_email", _no_user)
        for _ in range(2):
            assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 401
        assert len(verified) == 2
        assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 429
        assert len(verified) == 2

    def test_refusal_is_identical_for_known_and_unknown_email(self, client, monkeypatch) -> None:
        monkeypatch.setattr("backend.api.auth._user_by_email", _no_user)
        for _ in range(2):
            client.post("/api/auth/login", json=CREDENTIALS)
        known = client.post("/api/auth/login", json=CREDENTIALS)
        unknown = client.post("/api/auth/login", json={**CREDENTIALS, "email": "x@example.com"})
        assert known.status_code == unknown.status_code == 429
        assert known.json() == unknown.json() == {"detail": copy.RATE_LIMITED}

    def test_register_shares_the_auth_bucket(self, client, monkeypatch) -> None:
        monkeypatch.setattr("backend.api.auth._user_by_email", _no_user)
        for _ in range(2):
            client.post("/api/auth/login", json=CREDENTIALS)
        assert client.post("/api/auth/register", json=CREDENTIALS).status_code == 429


async def _no_user(db, email):
    return None


class TestDisabled:
    def test_zero_disables_the_bucket(self) -> None:
        settings = TIGHT.model_copy(update={"rate_limit_model_per_minute": 0})
        with make_client(settings) as c:
            assert all(
                c.post("/api/chat", json={"message": "hi"}).status_code == 401 for _ in range(5)
            )


class TestAdminRoutes:
    """food-table-admin: writes have their own bucket, separate from sign-in."""

    def test_third_admin_write_is_429(self) -> None:
        import uuid

        from backend.api.deps import get_current_user
        from backend.models import User

        admin = User(id=uuid.uuid7(), email="admin@example.com", hashed_password="x")
        app = create_app(settings=TIGHT)
        app.dependency_overrides[get_auth_settings] = lambda: TIGHT
        app.dependency_overrides[get_db] = _no_db
        app.dependency_overrides[get_current_user] = lambda: admin
        # No database here: the first two calls reach the handler and fail there (that is
        # not what is under test); the third must be refused before any work.
        with TestClient(app, raise_server_exceptions=False) as client:
            statuses = [
                client.post("/api/admin/foods/nope/deactivate").status_code for _ in range(3)
            ]
        assert statuses[0] != 429 and statuses[1] != 429 and statuses[2] == 429
        # And the auth bucket is untouched by admin writes.
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/api/auth/login", json=CREDENTIALS).status_code != 429
