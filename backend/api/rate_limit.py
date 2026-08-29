"""Per-client request rate limits (production-hardening spec).

A fixed window per ``(bucket, client)`` held in process memory: the service runs as one
process on one instance, so this is exact there and needs no store. It is a route
dependency rather than middleware so that the refusal is FastAPI's ordinary
``{"detail": ...}`` 429 -- which the frontend already renders -- and so that the request
middleware still stamps the request id and writes the access record for it. The client
address is a dictionary key here and nowhere else: it is never logged.
"""

import math
import time
from collections.abc import Callable, Mapping
from typing import Literal

from fastapi import HTTPException, Request, status

from backend.chat import copy

Bucket = Literal["model", "auth"]


class RateLimiter:
    def __init__(
        self,
        limits: Mapping[str, int],
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = dict(limits)
        self._window = window_seconds
        self._clock = clock
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def check(self, bucket: str, client: str) -> int | None:
        """Count one request. ``None`` admits it; otherwise whole seconds until the window resets.

        A bucket with limit 0 (or no limit configured) never refuses.
        """
        limit = self._limits.get(bucket, 0)
        if limit <= 0:
            return None
        now = self._clock()
        self._forget_expired(now)
        key = (bucket, client)
        started, count = self._windows.get(key, (now, 0))
        if count >= limit:
            return max(1, math.ceil(self._window - (now - started)))
        self._windows[key] = (started, count + 1)
        return None

    def _forget_expired(self, now: float) -> None:
        expired = [
            key for key, (started, _) in self._windows.items() if now - started >= self._window
        ]
        for key in expired:
            del self._windows[key]


def rate_limited(bucket: Bucket) -> Callable[[Request], None]:
    """Route dependency: 429 with ``Retry-After`` once this client exhausts ``bucket``.

    Declare it before the dependencies that do work (body parsing aside), so a refused
    request costs no database read, password verification, retrieval, or model call.
    """

    def dependency(request: Request) -> None:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return
        client = request.client.host if request.client is not None else "unknown"
        wait = limiter.check(bucket, client)
        if wait is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=copy.RATE_LIMITED,
                headers={"Retry-After": str(wait)},
            )

    return dependency
