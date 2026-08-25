"""Aggregate router for versioned API routes, mounted under ``/api``.

Empty by design on Day 1. Every meaningful route is user-scoped, and authorization does
not land until Day 6 -- exposing a child-profile read before then would ship exactly the
cross-user leak hard rule 9 forbids (see design.md Risk 6). Day 4 and Day 5 populate this.
"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
