"""Per-request correlation carried in ``contextvars`` (observability spec).

Three values follow a request through every ``await`` and into its streaming generator:
the request id (set by the middleware), the account id (set by ``get_current_user`` from
the session, never from a body), and the child profile id (set where the account's own
profile row is resolved). ``RequestContextFilter`` copies them onto every log record, so
the audit and routing emitters in ``backend/tools`` and ``backend/chat`` stay ignorant of
HTTP and identity while their records become correlatable.
"""

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_child_profile_id: ContextVar[str | None] = ContextVar("child_profile_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_user_id() -> str | None:
    return _user_id.get()


def set_user_id(value: uuid.UUID | str | None) -> None:
    _user_id.set(str(value) if value is not None else None)


def get_child_profile_id() -> str | None:
    return _child_profile_id.get()


def set_child_profile_id(value: uuid.UUID | str | None) -> None:
    _child_profile_id.set(str(value) if value is not None else None)


def reset_request_context() -> None:
    """Clear all three values in the current context (tests; middleware at request end)."""
    _request_id.set(None)
    _user_id.set(None)
    _child_profile_id.set(None)
