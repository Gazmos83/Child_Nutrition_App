"""Aggregate router for versioned API routes, mounted under ``/api``.

Public: ``/api/foods`` (the committed food table) and ``/api/auth/register``, ``/login``,
``/logout``. Everything else runs behind the session cookie (``backend/api/deps.py``):
``/api/children`` and its feeding log are the user-scoped records hard rule 9 binds to the
account, ``/api/chat`` reads the child's details and log from those rows rather than from
the request body, and ``/api/ask`` (Day 7) requires a session because an answer spends
model credit, while still reading no user data. The evaluation harness registers an
account before its first request.
"""

from fastapi import APIRouter

from backend.api.ask import router as ask_router
from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.children import router as children_router
from backend.api.foods import router as foods_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(ask_router)
api_router.include_router(chat_router)
api_router.include_router(children_router)
api_router.include_router(foods_router)
