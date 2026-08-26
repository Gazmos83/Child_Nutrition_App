"""Aggregate router for versioned API routes, mounted under ``/api``.

Only routes that are *not* user-scoped may live here until authorization lands on Day 6
(design.md Risk 6, hard rule 9). ``/api/ask`` qualifies: it reads no profile, persists
nothing, and takes no identity. Day 4 and Day 5 add user-scoped routes behind auth.
"""

from fastapi import APIRouter

from backend.api.ask import router as ask_router

api_router = APIRouter(prefix="/api")
api_router.include_router(ask_router)
