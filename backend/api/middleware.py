"""Request correlation, the per-request access record, and the last-resort error response.

A plain ASGI callable rather than ``BaseHTTPMiddleware`` (design.md Decision 3): it runs in
the request's own task, so the ``contextvars`` it sets are visible to every record emitted
downstream -- including late in a streaming response -- and the latency it measures covers
the whole stream. Unhandled exceptions are answered here too, because Starlette's
server-error layer runs *outside* this middleware, where the request context no longer
exists and the response header could not be added.
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import Headers, MutableHeaders

from backend.chat import copy
from backend.core import request_context

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REQUEST_ID_HEADER = "X-Request-ID"
# Probes are frequent and uninteresting; their access record is kept but demoted.
QUIET_PATHS = frozenset({"/health"})

access_logger = logging.getLogger("backend.api.access")
error_logger = logging.getLogger("backend.api.errors")


def _incoming_or_new_request_id(scope: Scope) -> str:
    """Honour a UUID-shaped incoming id (so a proxy's id threads through); else mint one."""
    incoming = Headers(scope=scope).get(REQUEST_ID_HEADER.lower())
    if incoming:
        try:
            return str(uuid.UUID(incoming.strip()))
        except ValueError:
            pass
    return str(uuid.uuid7())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_or_new_request_id(scope)
        request_context.set_request_id(request_id)
        started = time.perf_counter()
        status: int | None = None
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # One structured error record; the client gets a fixed message and the id.
            error_logger.exception(
                "unhandled error",
                extra={"method": scope["method"], "route": _route(scope)},
            )
            status = 500
            if not response_started:
                body = json.dumps({"detail": copy.SERVER_ERROR, "request_id": request_id}).encode()
                await send_with_request_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
        finally:
            route = _route(scope)
            latency_ms = int((time.perf_counter() - started) * 1000)
            access_logger.log(
                logging.DEBUG if route in QUIET_PATHS else logging.INFO,
                "%s %s %s %dms",
                scope["method"],
                route,
                status if status is not None else "-",
                latency_ms,
                extra={
                    "method": scope["method"],
                    "route": route,
                    "status": status,
                    "latency_ms": latency_ms,
                },
            )


def _route(scope: Scope) -> str:
    """The path with matched parameters put back as placeholders (``/api/children/{child_id}``).

    Derived from the raw path and ``path_params`` rather than the matched route object,
    whose ``path`` is relative to its own router and loses the ``/api`` prefix.
    """
    path: str = scope.get("path", "")
    for name, value in (scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path
