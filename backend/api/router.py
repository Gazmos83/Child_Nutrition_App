"""Aggregate router for versioned API routes, mounted under ``/api``.

Only routes that are *not* user-scoped may live here until authorization lands on Day 6
(design.md Risk 6, hard rule 9). ``/api/ask``, ``/api/chat``, ``/api/feedings``, and
``/api/foods`` all qualify: they read no profile, persist nothing, and take no identity --
``/api/chat``'s child details, history, and feeding log arrive in the request body, and
``/api/feedings`` hands the priced entry back for the browser to keep. Day 6 adds
user-scoped routes behind auth and makes ``/api/feedings`` persist.
"""

from fastapi import APIRouter

from backend.api.ask import router as ask_router
from backend.api.chat import router as chat_router
from backend.api.feedings import router as feedings_router
from backend.api.foods import router as foods_router

api_router = APIRouter(prefix="/api")
api_router.include_router(ask_router)
api_router.include_router(chat_router)
api_router.include_router(feedings_router)
api_router.include_router(foods_router)
