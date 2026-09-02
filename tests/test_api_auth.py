"""``/api/auth`` against PostgreSQL (authentication spec)."""

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import SESSION_COOKIE, get_auth_settings
from backend.auth.tokens import issue_session_token
from backend.core.config import Settings
from backend.models import User
from tests.conftest import FIXTURE_PASSWORD, TEST_SESSION_SECRET, sign_in

pytestmark = pytest.mark.db

CREDENTIALS = {"email": "new.parent@example.com", "password": "correct horse battery"}


class TestRegister:
    async def test_creates_the_account_and_signs_in(self, api_client: AsyncClient) -> None:
        response = await api_client.post("/api/auth/register", json=CREDENTIALS)
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "email", "is_admin"} and body["email"] == CREDENTIALS["email"]
        assert body["is_admin"] is False
        uuid.UUID(body["id"])
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}=")
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
        # The response never carries the hash or the token.
        assert "hashed_password" not in body and "token" not in body

        me = await api_client.get("/api/auth/me")
        assert me.status_code == 200 and me.json() == body

    async def test_duplicate_email_is_a_conflict(self, api_client: AsyncClient) -> None:
        assert (await api_client.post("/api/auth/register", json=CREDENTIALS)).status_code == 201
        variant = {**CREDENTIALS, "email": CREDENTIALS["email"].upper()}
        response = await api_client.post("/api/auth/register", json=variant)
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "body",
        [
            {"email": "not-an-email", "password": "correct horse battery"},
            {"email": "a@example.com", "password": "short"},
            {"email": "a@example.com", "password": "p" * 129},
            {"email": "a@example.com", "password": "correct horse battery", "admin": True},
            {"email": "a@example.com"},
        ],
    )
    async def test_invalid_credentials_shape_is_422(self, api_client: AsyncClient, body) -> None:
        assert (await api_client.post("/api/auth/register", json=body)).status_code == 422


class TestLogin:
    async def test_signs_in_with_the_right_password(self, api_client: AsyncClient, user: User):
        response = await api_client.post(
            "/api/auth/login", json={"email": user.email, "password": FIXTURE_PASSWORD}
        )
        assert response.status_code == 200 and response.json()["email"] == user.email
        assert SESSION_COOKIE in response.cookies
        assert (await api_client.get("/api/auth/me")).status_code == 200

    async def test_email_comparison_ignores_case(self, api_client: AsyncClient, user: User):
        response = await api_client.post(
            "/api/auth/login", json={"email": user.email.upper(), "password": FIXTURE_PASSWORD}
        )
        assert response.status_code == 200

    async def test_wrong_password_and_unknown_email_are_indistinguishable(
        self, api_client: AsyncClient, user: User
    ) -> None:
        wrong = await api_client.post(
            "/api/auth/login", json={"email": user.email, "password": "wrong horse battery"}
        )
        unknown = await api_client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": FIXTURE_PASSWORD}
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()
        assert "set-cookie" not in wrong.headers and "set-cookie" not in unknown.headers

    async def test_inactive_account_cannot_sign_in(
        self, api_client: AsyncClient, db_session: AsyncSession, user: User
    ) -> None:
        user.is_active = False
        await db_session.commit()
        response = await api_client.post(
            "/api/auth/login", json={"email": user.email, "password": FIXTURE_PASSWORD}
        )
        assert response.status_code == 401


class TestSession:
    async def test_no_cookie_is_401(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/auth/me")
        assert response.status_code == 401 and response.json() == {"detail": "Sign in to continue"}

    async def test_tampered_token_is_401(self, api_client: AsyncClient, user: User) -> None:
        forged = issue_session_token(user.id, "another-secret" * 4, dt.timedelta(hours=1))
        api_client.cookies.set(SESSION_COOKIE, forged)
        assert (await api_client.get("/api/auth/me")).status_code == 401

    async def test_expired_token_is_401(self, api_client: AsyncClient, user: User) -> None:
        api_client.cookies.set(
            SESSION_COOKIE,
            issue_session_token(user.id, TEST_SESSION_SECRET, dt.timedelta(seconds=-5)),
        )
        assert (await api_client.get("/api/auth/me")).status_code == 401

    async def test_token_for_a_deleted_account_is_401(
        self, api_client: AsyncClient, db_session: AsyncSession, user: User
    ) -> None:
        sign_in(api_client, user)
        await db_session.delete(user)
        await db_session.commit()
        assert (await api_client.get("/api/auth/me")).status_code == 401

    async def test_deactivated_account_is_refused_immediately(
        self, auth_client: AsyncClient, db_session: AsyncSession, user: User
    ) -> None:
        assert (await auth_client.get("/api/auth/me")).status_code == 200
        user.is_active = False
        await db_session.commit()
        assert (await auth_client.get("/api/auth/me")).status_code == 401

    async def test_logout_clears_the_cookie(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post("/api/auth/logout")
        assert response.status_code == 204
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f'{SESSION_COOKIE}="";') or "Max-Age=0" in cookie


class TestNothingSensitiveIsLogged:
    """Observability spec: credentials, tokens, and emails never reach a log record."""

    async def test_register_and_sign_in_leave_no_credential_trace(
        self, api_client: AsyncClient, caplog
    ) -> None:
        import logging as _logging

        caplog.set_level(_logging.DEBUG)
        registered = await api_client.post("/api/auth/register", json=CREDENTIALS)
        assert registered.status_code == 201
        cookie = registered.cookies.get(SESSION_COOKIE)
        assert cookie
        api_client.cookies.clear()
        signed_in = await api_client.post("/api/auth/login", json=CREDENTIALS)
        assert signed_in.status_code == 200
        assert (await api_client.get("/api/auth/me")).status_code == 200

        captured = "\n".join(
            r.getMessage() + " " + repr({k: v for k, v in r.__dict__.items() if k != "msg"})
            for r in caplog.records
        )
        assert CREDENTIALS["password"] not in captured
        assert CREDENTIALS["email"] not in captured
        assert cookie not in captured
        assert "$argon2" not in captured
        # The access records are there, carrying only the account's identifier.
        access = [r for r in caplog.records if r.name == "backend.api.access"]
        assert [r.status for r in access] == [201, 200, 200]
        assert access[-1].user_id == registered.json()["id"]


class TestAdminFlag:
    """food-table-admin: the account read says whether the caller may edit the food table."""

    async def test_listed_email_is_admin_regardless_of_case(
        self, api_client: AsyncClient, user: User
    ) -> None:
        app = api_client._transport.app  # type: ignore[attr-defined]
        admin_settings = Settings(
            database_url="postgresql://unused:unused@unused/unused",
            session_secret=TEST_SESSION_SECRET,
            admin_emails=user.email.upper(),
            _env_file=None,
        )
        app.dependency_overrides[get_auth_settings] = lambda: admin_settings
        sign_in(api_client, user)
        me = await api_client.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["is_admin"] is True

    async def test_unlisted_email_is_not_admin(self, auth_client: AsyncClient) -> None:
        me = await auth_client.get("/api/auth/me")
        assert me.json()["is_admin"] is False
