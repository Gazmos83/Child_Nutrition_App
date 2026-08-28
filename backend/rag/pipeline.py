"""The shared answer step (Day 3 design.md Decisions 1, 7, 8, 14).

Retrieval strategy is a parameter; everything here -- relevance floor, context, prompt,
tone, disclaimer -- is identical for both strategies.
"""

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from backend.db.knowledge_store import Document
from backend.rag.prompts import (
    DISCLAIMER,
    NO_ANSWER_MESSAGE,
    SYSTEM_PROMPT,
    build_context,
    build_user_prompt,
)
from backend.rag.retrievers import RetrievalResult, Retriever, _content_text
from backend.schemas.rag import Citation, RetrievalMeta, Strategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagResponse:
    answer: str
    citations: list[Citation]
    disclaimer: str
    strategy: Strategy
    retrieval: RetrievalMeta


@dataclass
class RetrievedContext:
    """Retrieval + context construction for one question, without generation (Day 5 seam)."""

    result: RetrievalResult
    kept: list[Document]
    context: str
    citations: list[Citation]
    top_score: float | None


class RagPipeline:
    def __init__(
        self,
        retrievers: dict[Strategy, Retriever],
        chat_model: BaseChatModel,
        min_similarity: float = 0.45,
        context_char_budget: int = 6000,
    ) -> None:
        if not retrievers:
            raise ValueError("At least one retriever is required")
        self.retrievers = retrievers
        self.chat_model = chat_model
        self.min_similarity = min_similarity
        self.context_char_budget = context_char_budget

    # -- shared steps -------------------------------------------------------------------

    def _retriever(self, strategy: Strategy) -> Retriever:
        try:
            return self.retrievers[strategy]
        except KeyError:
            raise ValueError(f"Unknown strategy {strategy!r}") from None

    async def retrieve(self, question: str, strategy: Strategy) -> RetrievedContext:
        started = time.perf_counter()
        result = await self._retriever(strategy).retrieve(question)
        latency_ms = int((time.perf_counter() - started) * 1000)
        scores = [c.score for c in result.chunks if c.score is not None]
        top_score = max(scores) if scores else None
        # The floor is judged on the original question's own best match (Decision 7): a
        # paraphrase may pull in extra context, but must not turn an out-of-domain
        # question into an answered one.
        gate = result.question_top_score if result.question_top_score is not None else top_score
        in_domain = gate is None or gate >= self.min_similarity
        kept = (
            [c for c in result.chunks if c.score is None or c.score >= self.min_similarity]
            if in_domain
            else []
        )
        context, citations = build_context(kept, self.context_char_budget)
        logger.info(
            "rag strategy=%s queries=%d retrieved=%d above_floor=%d in_context=%d top=%.3f",
            strategy,
            len(result.queries),
            result.retrieved,
            len(kept),
            len(citations),
            top_score if top_score is not None else float("nan"),
            # Structured fields for the JSON log; the queries are what the client already
            # receives in RetrievalMeta, so nothing new is exposed.
            extra={
                "strategy": strategy,
                "queries": list(result.queries),
                "retrieved": result.retrieved,
                "kept": len(kept),
                "top_score": top_score,
                "latency_ms": latency_ms,
            },
        )
        return RetrievedContext(result, kept, context, citations, top_score)

    def messages(self, question: str, context: str) -> list[BaseMessage]:
        """The exact prompt sent to the model -- identical for every strategy."""
        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_user_prompt(question, context)),
        ]

    def retrieval_meta(self, prepared: RetrievedContext, strategy: Strategy) -> RetrievalMeta:
        return RetrievalMeta(
            strategy=strategy,
            queries=prepared.result.queries,
            filters=prepared.result.filters,
            filter_dropped=prepared.result.filter_dropped,
            retrieved=prepared.result.retrieved,
            kept=len(prepared.citations),
            top_score=prepared.top_score,
        )

    def _no_answer(self, prepared: RetrievedContext, strategy: Strategy) -> RagResponse:
        return RagResponse(
            answer=NO_ANSWER_MESSAGE,
            citations=[],
            disclaimer=DISCLAIMER,
            strategy=strategy,
            retrieval=self.retrieval_meta(prepared, strategy),
        )

    # -- public API ---------------------------------------------------------------------

    async def answer(self, question: str, strategy: Strategy = "advanced") -> RagResponse:
        prepared = await self.retrieve(question, strategy)
        if not prepared.citations:
            return self._no_answer(prepared, strategy)
        reply = await self.chat_model.ainvoke(self.messages(question, prepared.context))
        return RagResponse(
            answer=_content_text(reply.content).strip(),
            citations=prepared.citations,
            disclaimer=DISCLAIMER,
            strategy=strategy,
            retrieval=self.retrieval_meta(prepared, strategy),
        )

    async def stream(
        self, question: str, strategy: Strategy = "advanced"
    ) -> AsyncIterator[str | RagResponse]:
        """Yield answer text fragments, then the complete ``RagResponse`` as the last item.

        The no-answer message is yielded as a single fragment so clients see one shape.
        """
        prepared = await self.retrieve(question, strategy)
        if not prepared.citations:
            response = self._no_answer(prepared, strategy)
            yield response.answer
            yield response
            return
        parts: list[str] = []
        async for chunk in self.chat_model.astream(self.messages(question, prepared.context)):
            text = _content_text(chunk.content)
            if text:
                parts.append(text)
                yield text
        yield RagResponse(
            answer="".join(parts).strip(),
            citations=prepared.citations,
            disclaimer=DISCLAIMER,
            strategy=strategy,
            retrieval=self.retrieval_meta(prepared, strategy),
        )
