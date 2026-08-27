"""``POST /api/chat`` -- the routed assistant (Day 5 chat-api spec).

Not user-scoped: the child's details and the conversation history arrive in the request
body, nothing is persisted, and no identity is taken. Streaming uses the same hand-formatted
server-sent events as ``/api/ask``; the event order is ``route``, ``tool``..., ``token``...,
``final``, ``done`` (design.md Decision 6).
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.sse import sse
from backend.chat import copy
from backend.chat.service import ChatService
from backend.chat.wiring import get_chat_service
from backend.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def get_service() -> ChatService:
    """Dependency: the process-wide service, or 503 naming the missing configuration."""
    try:
        return get_chat_service()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def _event_stream(service: ChatService, request: ChatRequest) -> AsyncIterator[str]:
    try:
        async for event in service.stream(request):
            yield sse(event.event, event.data)
    except Exception:
        logger.exception("Chat stream failed")
        yield sse("error", {"message": copy.STREAM_FAILED})


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the child-nutrition assistant",
    responses={
        200: {
            "description": (
                "JSON answer when `stream` is false; otherwise a `text/event-stream` of one "
                "`route` event, a `tool` event per tool invocation, `token` events, one "
                "`final` event, then `done` (or a terminal `error`)."
            )
        },
        503: {"description": "Language-model provider or knowledge base is not configured."},
    },
)
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_service)],
) -> ChatResponse | StreamingResponse:
    """Route the message to the knowledge base, the nutrient tools, or both, and answer.

    Stateless: the child's details and history live only in this request.
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
