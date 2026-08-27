"""Aggregate router for versioned API routes, mounted under ``/api``.

Only routes that are *not* user-scoped may live here until authorization lands on Day 6
(design.md Risk 6, hard rule 9). ``/api/ask`` and ``/api/chat`` both qualify: they read no
profile, persist nothing, and take no identity -- ``/api/chat``'s child details and history
arrive in the request body. Day 6 adds user-scoped routes behind auth.
"""

from fastapi import APIRouter

from backend.api.ask import router as ask_router
from backend.api.chat import router as chat_router

api_router = APIRouter(prefix="/api")
api_router.include_router(ask_router)
api_router.include_router(chat_router)
