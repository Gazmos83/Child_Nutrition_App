"""``POST /api/ask`` -- ask the nutrition assistant a question (Day 3 ask-api spec).

Requires a session since Day 7 -- the answer costs model credit -- but is not user-scoped:
it reads no child profile, persists nothing, and uses the identity for admission only.
Streaming uses hand-formatted server-sent events over ``StreamingResponse`` (design
Decision 10).
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.deps import CurrentUser
from backend.api.rate_limit import rate_limited
from backend.api.sse import sse
from backend.core import request_context
from backend.rag.llm import get_pipeline
from backend.rag.pipeline import RagPipeline, RagResponse
from backend.schemas.rag import AskRequest, AskResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])


def get_rag_pipeline() -> RagPipeline:
    """Dependency: the process-wide pipeline, or 503 naming the missing configuration."""
    try:
        return get_pipeline()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def to_ask_response(response: RagResponse) -> AskResponse:
    return AskResponse(
        answer=response.answer,
        citations=response.citations,
        disclaimer=response.disclaimer,
        strategy=response.strategy,
        retrieval=response.retrieval,
    )


async def _event_stream(pipeline: RagPipeline, request: AskRequest) -> AsyncIterator[str]:
    try:
        async for item in pipeline.stream(request.question, request.strategy):
            if isinstance(item, RagResponse):
                final = to_ask_response(item)
                yield sse(
                    "citations",
                    {
                        "citations": [c.model_dump() for c in final.citations],
                        "retrieval": final.retrieval.model_dump(),
                        "disclaimer": final.disclaimer,
                        "strategy": final.strategy,
                    },
                )
            else:
                yield sse("token", {"text": item})
        yield sse("done", {})
    except Exception:
        logger.exception("Streaming answer failed")
        yield sse(
            "error",
            {
                "message": "The answer could not be completed. Please try again.",
                "request_id": request_context.get_request_id(),
            },
        )


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a child-nutrition question",
    # Runs before every parameter dependency: a refused request costs nothing downstream.
    dependencies=[Depends(rate_limited("model"))],
    responses={
        200: {
            "description": (
                "JSON answer when `stream` is false; otherwise a `text/event-stream` of "
                "`token` events, one `citations` event, then `done` (or `error`)."
            )
        },
        401: {"description": "No valid session."},
        429: {"description": "This client has asked too often in the last minute."},
        503: {"description": "Language-model provider or knowledge base is not configured."},
    },
)
async def ask(
    request: AskRequest,
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
    _user: CurrentUser,
) -> AskResponse | StreamingResponse:
    """Answer from the pediatric-guideline knowledge base with citations and a disclaimer.

    Stateless: nothing about the request is stored and no user data is read. The session
    only decides whether the caller may spend model credit.
    """
    if request.stream:
        return StreamingResponse(
            _event_stream(pipeline, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        response = await pipeline.answer(request.question, request.strategy)
    except RuntimeError as exc:
        # Knowledge base missing, provider unreachable: a dependency problem, not a bug.
        logger.warning("Answer failed: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return to_ask_response(response)
