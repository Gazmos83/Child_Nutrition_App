"""``POST /api/ask`` -- ask the nutrition assistant a question (Day 3 ask-api spec).

Not user-scoped: reads no child profile, persists nothing, takes no identity. Streaming
uses hand-formatted server-sent events over ``StreamingResponse`` (design Decision 10).
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

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


def sse(event: str, data: object) -> str:
    """One server-sent event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
        yield sse("error", {"message": "The answer could not be completed. Please try again."})


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a child-nutrition question",
    responses={
        200: {
            "description": (
                "JSON answer when `stream` is false; otherwise a `text/event-stream` of "
                "`token` events, one `citations` event, then `done` (or `error`)."
            )
        },
        503: {"description": "Language-model provider or knowledge base is not configured."},
    },
)
async def ask(
    request: AskRequest,
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
) -> AskResponse | StreamingResponse:
    """Answer from the pediatric-guideline knowledge base with citations and a disclaimer.

    Stateless: nothing about the request is stored and no user data is read.
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
