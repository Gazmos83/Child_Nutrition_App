"""Signed, stateless session tokens (JWT, HS256).

The token names one account and an expiry; nothing else. It travels in an HttpOnly cookie
(see ``backend/api/auth.py``), never in a response body. Stateless on purpose: the only
feature server-side sessions would add is revocation-before-expiry, and the one place
that matters -- a deactivated account -- is covered because every request re-reads the
user row and checks ``is_active``.
"""

import datetime as dt
import uuid

import jwt

ALGORITHM = "HS256"


def issue_session_token(user_id: uuid.UUID, secret: str, ttl: dt.timedelta) -> str:
    now = dt.datetime.now(dt.UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + ttl}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def read_session_token(token: str, secret: str) -> uuid.UUID | None:
    """The account the token names, or ``None`` if it is invalid, expired, or tampered."""
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
        return uuid.UUID(claims["sub"])
    except jwt.PyJWTError, KeyError, ValueError:
        return None
