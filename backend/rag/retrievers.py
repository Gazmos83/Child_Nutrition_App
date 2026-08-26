"""Retrieval strategies (Day 3 design.md Decisions 1, 2, 5, 6).

``BasicRetriever``: embed the question, take top-K.
``AdvancedRetriever``: deterministic age extraction -> validated metadata filter ->
model-generated paraphrases -> multi-query search -> reciprocal rank fusion -> near-
duplicate removal -> drop-and-retry if the filter emptied results -> top-K.

Both return a ``RetrievalResult``; everything downstream (relevance floor, context,
prompt, answer) is shared, so Day 6's A/B isolates retrieval.
"""

import asyncio
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from backend.db.knowledge_store import Document, KnowledgeStore, SearchFilter
from backend.rag.prompts import TRANSLATE_SYSTEM_PROMPT
from backend.rag.query_analysis import extract_age_range
from backend.schemas.rag import Strategy

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class RetrievalResult:
    """Ranked passages plus a record of how they were obtained."""

    chunks: list[Document]
    queries: list[str]
    filters: dict[str, object] = field(default_factory=dict)
    filter_dropped: bool = False
    question_top_score: float | None = None
    """Best similarity achieved by the *original* question alone. The relevance floor is
    judged against this, so paraphrases can add context but never unlock an answer."""

    @property
    def retrieved(self) -> int:
        return len(self.chunks)


class Retriever(Protocol):
    name: Strategy

    async def retrieve(self, question: str) -> RetrievalResult: ...


class BasicRetriever:
    """Single query, top-K, no filters."""

    name: Strategy = "basic"

    def __init__(self, store: KnowledgeStore, top_k: int = 6) -> None:
        self.store = store
        self.top_k = top_k

    async def retrieve(self, question: str) -> RetrievalResult:
        chunks = await self.store.search(question, top_k=self.top_k)
        return RetrievalResult(
            chunks=chunks, queries=[question], question_top_score=_top_score(chunks)
        )


def _top_score(ranked: list[Document]) -> float | None:
    scores = [d.score for d in ranked if d.score is not None]
    return max(scores) if scores else None


def chunk_key(doc: Document) -> tuple[str, int]:
    return (doc.document_id or doc.source, doc.chunk_index)


def reciprocal_rank_fusion(ranked_lists: Iterable[list[Document]], k: int = 60) -> list[Document]:
    """Fuse ranked lists: score = sum over lists of 1 / (k + rank).

    A chunk found by several queries outranks one found by one, all else equal. The
    chunk's ``score`` is set to the *maximum* cosine similarity it achieved in any list,
    for the relevance floor downstream. Deterministic: ties break on that score, then key.
    """
    fused: dict[tuple[str, int], float] = {}
    best: dict[tuple[str, int], Document] = {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            key = chunk_key(doc)
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
            current = best.get(key)
            if current is None or (doc.score or 0.0) > (current.score or 0.0):
                best[key] = doc
    ordered = sorted(fused, key=lambda key: (-fused[key], -(best[key].score or 0.0), key))
    return [best[key] for key in ordered]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def deduplicate(chunks: list[Document], containment: float = 0.8) -> list[Document]:
    """Drop repeated chunks, then chunks whose text is mostly contained in a higher-ranked
    chunk of the same document (chunk-overlap artefacts)."""
    kept: list[Document] = []
    seen: set[tuple[str, int]] = set()
    kept_tokens: list[tuple[str | None, set[str]]] = []
    for doc in chunks:
        key = chunk_key(doc)
        if key in seen:
            continue
        seen.add(key)
        tokens = _tokens(doc.content)
        duplicate = False
        for other_doc_id, other_tokens in kept_tokens:
            if other_doc_id != doc.document_id or not tokens:
                continue
            if len(tokens & other_tokens) / len(tokens) >= containment:
                duplicate = True
                break
        if duplicate:
            continue
        kept.append(doc)
        kept_tokens.append((doc.document_id, tokens))
    return kept


def _parse_alternatives(text: str, original: str, limit: int) -> list[str]:
    """Extract a JSON array of strings from a model reply, tolerating code fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    seen = {original.strip().lower()}
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        candidate = " ".join(item.split())
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        result.append(candidate)
        if len(result) >= limit:
            break
    return result


def _content_text(content: object) -> str:
    """LangChain 1.x message content may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


class AdvancedRetriever:
    """Query analysis, translation, multi-query fusion, filtering, dedup."""

    name: Strategy = "advanced"

    def __init__(
        self,
        store: KnowledgeStore,
        chat_model: BaseChatModel | None,
        top_k_per_query: int = 8,
        top_k_final: int = 6,
        max_alternatives: int = 3,
        rrf_k: int = 60,
    ) -> None:
        self.store = store
        self.chat_model = chat_model
        self.top_k_per_query = top_k_per_query
        self.top_k_final = top_k_final
        self.max_alternatives = max_alternatives
        self.rrf_k = rrf_k

    async def translate(self, question: str) -> list[str]:
        """1-3 alternative phrasings, or [] on any failure (Decision 2: degrade, never error)."""
        if self.chat_model is None or self.max_alternatives <= 0:
            return []
        try:
            reply = await self.chat_model.ainvoke(
                [
                    SystemMessage(content=TRANSLATE_SYSTEM_PROMPT.format(n=self.max_alternatives)),
                    HumanMessage(content=question),
                ]
            )
            alternatives = _parse_alternatives(
                _content_text(reply.content), question, self.max_alternatives
            )
        except Exception as exc:
            logger.warning("Query translation failed; retrieving with the original only: %s", exc)
            return []
        if not alternatives:
            logger.info("Query translation produced no usable alternatives")
        return alternatives

    async def _search_all(
        self, queries: list[str], filter: SearchFilter | None
    ) -> tuple[list[Document], float | None]:
        """Fused ranking plus the original question's own top score (queries[0])."""
        ranked_lists = await asyncio.gather(
            *(self.store.search(q, top_k=self.top_k_per_query, filter=filter) for q in queries)
        )
        return reciprocal_rank_fusion(ranked_lists, k=self.rrf_k), _top_score(ranked_lists[0])

    async def retrieve(self, question: str) -> RetrievalResult:
        age = extract_age_range(question)
        search_filter = (
            SearchFilter(age_min_months=age.min_months, age_max_months=age.max_months)
            if age
            else None
        )
        queries = [question, *await self.translate(question)]

        fused, question_top = await self._search_all(queries, search_filter)
        dropped = False
        if not fused and search_filter is not None and search_filter.has_age:
            logger.info("Age filter %s eliminated every passage; retrying without it", age)
            fused, question_top = await self._search_all(queries, None)
            dropped = True

        chunks = deduplicate(fused)[: self.top_k_final]
        filters: dict[str, object] = {}
        if search_filter is not None and not dropped:
            filters = {
                "age_min_months": search_filter.age_min_months,
                "age_max_months": search_filter.age_max_months,
            }
        return RetrievalResult(
            chunks=chunks,
            queries=queries,
            filters=filters,
            filter_dropped=dropped,
            question_top_score=question_top,
        )
