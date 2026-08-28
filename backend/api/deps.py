"""Shared request dependencies: the database session and the authenticated user.

``get_current_user`` is the authorization anchor for every user-scoped route (hard rule
9): it turns the session cookie into a ``User`` row or a 401, and nothing downstream ever
sees a request that reached it without one. ``owned_child`` is the single place the
ownership predicate is written, so no route can forget it.
"""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.tokens import read_session_token
from backend.core import request_context
from backend.core.config import Settings, get_settings
from backend.db.session import get_db
from backend.models import ChildProfile, User

SESSION_COOKIE = "session"

UNAUTHENTICATED_DETAIL = "Sign in to continue"
NO_SUCH_CHILD_DETAIL = "No such child profile"


def unauthenticated() -> HTTPException:
    """The one response for every refusal of an unauthenticated request: no hint about why."""
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_DETAIL)


def no_such_child() -> HTTPException:
    """Non-owner and nonexistent are the same answer, byte for byte (user-account spec: the
    response does not reveal whether that profile exists)."""
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_CHILD_DETAIL)


def get_auth_settings() -> Settings:
    """Settings with a session secret, or 503 naming the missing configuration."""
    settings = get_settings()
    if settings.session_secret is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SESSION_SECRET is not configured; authentication is unavailable",
        )
    return settings


DbSession = Annotated[AsyncSession, Depends(get_db)]
AuthSettings = Annotated[Settings, Depends(get_auth_settings)]


async def get_current_user(
    db: DbSession,
    settings: AuthSettings,
    session: Annotated[str | None, Cookie()] = None,
) -> User:
    """The active account the session cookie names, or 401."""
    if session is None:
        raise unauthenticated()
    user_id = read_session_token(session, settings.session_secret or "")
    if user_id is None:
        raise unauthenticated()
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthenticated()
    # Correlation for every log record in this request (observability spec): the id comes
    # from the session cookie just verified, never from the body.
    request_context.set_user_id(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def owned_child(child_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ChildProfile:
    """The caller's own child profile with the given id, or 404.

    The ``user_id`` predicate here is the authorization boundary for every child-scoped
    route (hard rule 9). 404 rather than 403 so that a probe cannot learn whether an id
    exists.
    """
    result = await db.execute(
        select(ChildProfile).where(ChildProfile.id == child_id, ChildProfile.user_id == user.id)
    )
    child = result.scalar_one_or_none()
    if child is None:
        raise no_such_child()
    request_context.set_child_profile_id(child.id)
    return child


OwnedChild = Annotated[ChildProfile, Depends(owned_child)]
