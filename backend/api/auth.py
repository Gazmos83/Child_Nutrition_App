"""``/api/auth`` -- register, sign in, sign out, and who-am-I (authentication spec).

The session is a signed token in an HttpOnly, SameSite=Lax cookie. The browser talks to
one origin (the Next.js rewrite proxies ``/api``), so the cookie rides along on every
``fetch`` with no client-side token handling, and script cannot read it. SameSite=Lax
plus JSON-only bodies is the CSRF posture: a cross-site form post carries neither the
cookie nor an acceptable content type.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.api.deps import SESSION_COOKIE, AuthSettings, CurrentUser, DbSession
from backend.api.rate_limit import rate_limited
from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import issue_session_token
from backend.core.config import Settings
from backend.models import User
from backend.schemas.auth import Credentials, CurrentUserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for unknown email and wrong password alike.
BAD_CREDENTIALS_DETAIL = "That email and password don't match"


def _set_session_cookie(response: Response, user: User, settings: Settings) -> None:
    ttl = dt.timedelta(hours=settings.session_ttl_hours)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session_token(user.id, settings.session_secret or "", ttl),
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        # Plain http://localhost in development; everywhere else the cookie is HTTPS-only.
        secure=settings.app_env != "dev",
        path="/",
    )


async def _user_by_email(db: DbSession, email: str) -> User | None:
    result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    return result.scalar_one_or_none()


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=CurrentUserResponse,
    summary="Create an account and sign in",
    # Before any hashing: a refused attempt does no password work.
    dependencies=[Depends(rate_limited("auth"))],
    responses={
        409: {"description": "An account with this email already exists."},
        429: {"description": "Too many attempts from this client in the last minute."},
    },
)
async def register(
    credentials: Credentials, response: Response, db: DbSession, settings: AuthSettings
) -> CurrentUserResponse:
    user = User(email=credentials.email, hashed_password=hash_password(credentials.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # uq_users_email_lower: the database is the arbiter of uniqueness, so two
        # simultaneous registrations cannot both succeed.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        ) from exc
    _set_session_cookie(response, user, settings)
    return CurrentUserResponse(id=user.id, email=user.email)


@router.post(
    "/login",
    response_model=CurrentUserResponse,
    summary="Sign in",
    dependencies=[Depends(rate_limited("auth"))],
    responses={
        401: {"description": "Unknown email or wrong password (not distinguished)."},
        429: {"description": "Too many attempts from this client in the last minute."},
    },
)
async def login(
    credentials: Credentials, response: Response, db: DbSession, settings: AuthSettings
) -> CurrentUserResponse:
    user = await _user_by_email(db, credentials.email)
    # verify_password runs even when the user is missing, so timing does not reveal
    # which of the two was wrong.
    hashed = user.hashed_password if user is not None else None
    if not verify_password(hashed, credentials.password) or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=BAD_CREDENTIALS_DETAIL)
    _set_session_cookie(response, user, settings)
    return CurrentUserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
async def logout(response: Response) -> None:
    """Clear the cookie. The token itself stays valid until it expires (stateless sessions)."""
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=CurrentUserResponse, summary="The signed-in account")
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(id=user.id, email=user.email)
