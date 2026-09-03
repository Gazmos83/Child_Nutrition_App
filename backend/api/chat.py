"""``POST /api/chat`` -- the routed assistant (chat-api spec).

Authenticated since Day 6. ``resolve_chat_request`` is the authority seam: the child's
details and feeding log come from the signed-in account's own rows, never from the body,
and the conversation history is the only thing the browser supplies. Streaming uses the
same hand-formatted server-sent events as ``/api/ask``; the event order is ``route``,
``tool``..., ``token``..., ``final``, ``done`` (Day 5 design.md Decision 6).
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from backend.api.children import (
    DEFAULT_LOG_DAYS,
    child_context_or_422,
    recent_feedings,
    to_feeding_entries,
)
from backend.api.deps import AuthSettings, CurrentUser, DbSession, is_admin, owned_child
from backend.api.rate_limit import rate_limited
from backend.api.sse import sse
from backend.chat import copy
from backend.chat.service import ChatService
from backend.chat.wiring import get_chat_service
from backend.core import request_context
from backend.models import ChildProfile
from backend.schemas.chat import ChatRequest, ChatRequestBody, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def get_service() -> ChatService:
    """Dependency: the process-wide service, or 503 naming the missing configuration."""
    try:
        return get_chat_service()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def resolve_chat_request(
    body: ChatRequestBody, user: CurrentUser, db: DbSession, settings: AuthSettings
) -> ChatRequest:
    """The authority seam: fill ``child``, ``feeding_log``, and ``is_admin`` from the
    caller's own rows and session -- never from the body (hard rules 9 and 10).

    ``child_id`` names one of the caller's children (an unowned id is refused exactly like a
    nonexistent one). Omitted, it means the account's only child; with several children it
    is required; with none the request proceeds without child context and the service's
    existing "details go in the side panel" path applies.
    """
    admin = is_admin(user, settings)
    if body.child_id is not None:
        child = await owned_child(body.child_id, user, db)
    else:
        result = await db.execute(
            select(ChildProfile).where(ChildProfile.user_id == user.id).limit(2)
        )
        children = list(result.scalars())
        if len(children) > 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="child_id is required when the account has more than one child",
            )
        child = children[0] if children else None
    if child is None:
        return ChatRequest(**body.model_dump(), is_admin=admin)
    request_context.set_child_profile_id(child.id)
    rows = await recent_feedings(db, child, DEFAULT_LOG_DAYS)
    return ChatRequest(
        **body.model_dump(),
        child=child_context_or_422(child),
        feeding_log=to_feeding_entries(rows),
        is_admin=admin,
    )


async def _event_stream(service: ChatService, request: ChatRequest) -> AsyncIterator[str]:
    try:
        async for event in service.stream(request):
            yield sse(event.event, event.data)
    except Exception:
        logger.exception("Chat stream failed")
        yield sse(
            "error",
            {"message": copy.STREAM_FAILED, "request_id": request_context.get_request_id()},
        )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the child-nutrition assistant",
    # Runs before every parameter dependency: a refused request costs nothing downstream.
    dependencies=[Depends(rate_limited("model"))],
    responses={
        200: {
            "description": (
                "JSON answer when `stream` is false; otherwise a `text/event-stream` of one "
                "`route` event, a `tool` event per tool invocation, `token` events, one "
                "`final` event, then `done` (or a terminal `error`)."
            )
        },
        401: {"description": "No valid session."},
        429: {"description": "This client has asked too often in the last minute."},
        503: {"description": "Language-model provider or knowledge base is not configured."},
    },
)
async def chat(
    request: Annotated[ChatRequest, Depends(resolve_chat_request)],
    service: Annotated[ChatService, Depends(get_service)],
) -> ChatResponse | StreamingResponse:
    """Route the message to the knowledge base, the nutrient tools, or both, and answer.

    Nothing about the conversation is stored; the child's details and log are read from
    the account (``resolve_chat_request``) for this request only.
    """
    if request.stream:
        return StreamingResponse(
            _event_stream(service, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        return await service.answer(request)
    except RuntimeError as exc:
        # Knowledge base missing, provider unreachable: a dependency problem, not a bug.
        logger.warning("Chat answer failed: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
