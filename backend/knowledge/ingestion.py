"""Incremental, idempotent knowledge-base ingestion (Day 3 task 4.1).

load corpus -> chunk -> hash -> compare with what the store already holds -> embed only
new/changed documents -> replace each document's chunks -> summarise.

``scripts/ingest.py`` is the command-line entry point; this module is importable so the
pipeline can be tested with a stub embedder against a temporary database.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.db.knowledge_store import Document, Embedder, KnowledgeStore
from backend.knowledge.chunker import chunk_documents
from backend.knowledge.hashing import content_hash
from backend.knowledge.loaders import load_corpus

logger = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    """What a run did. Every count is logged so an operator can see the final state."""

    loaded: int = 0
    unchanged: int = 0
    new: int = 0
    changed: int = 0
    chunks_embedded: int = 0
    chunks_upserted: int = 0
    stale_document_ids: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def processed(self) -> int:
        return self.new + self.changed


async def run_ingestion(
    corpus_dir: str | Path,
    store: KnowledgeStore,
    embedder: Embedder,
) -> IngestionSummary:
    """Ingest ``corpus_dir`` into ``store``, embedding only new or changed documents.

    Raises:
        FileNotFoundError: if the corpus directory does not exist.
        ValueError: if the manifest is invalid.
        RuntimeError: if embedding or the store fails (nothing partial is left behind
            for the document being processed: each document is replaced as a unit).
    """
    started = time.perf_counter()
    summary = IngestionSummary()

    logger.info("Loading corpus from %s", corpus_dir)
    documents = load_corpus(corpus_dir)
    summary.loaded = len(documents)
    if not documents:
        logger.warning("No documents to ingest")
        summary.elapsed_seconds = time.perf_counter() - started
        return summary

    existing = await store.list_document_hashes()
    logger.info("Store currently holds %d documents", len(existing))

    to_process: list[dict] = []
    for doc in documents:
        doc["content_hash"] = content_hash(doc["content"])
        doc_id = doc["document_id"]
        previous = existing.get(doc_id)
        if previous == doc["content_hash"]:
            summary.unchanged += 1
            logger.debug("unchanged  %s", doc_id)
        elif previous is None:
            summary.new += 1
            logger.info("new        %s (%s)", doc_id, doc["source"])
            to_process.append(doc)
        else:
            summary.changed += 1
            logger.info("changed    %s (%s)", doc_id, doc["source"])
            to_process.append(doc)

    corpus_ids = {doc["document_id"] for doc in documents}
    summary.stale_document_ids = sorted(set(existing) - corpus_ids)
    for stale in summary.stale_document_ids:
        logger.warning(
            "Store holds %s but it is no longer in the corpus; left in place "
            "(delete it with the store's delete() if that is intended)",
            stale,
        )

    if not to_process:
        logger.info("Nothing new or changed; no embeddings computed")
        summary.elapsed_seconds = time.perf_counter() - started
        _log_summary(summary)
        return summary

    chunks = chunk_documents(to_process)
    logger.info(
        "Embedding %d chunks from %d documents with %s",
        len(chunks),
        len(to_process),
        embedder.model_name,
    )
    embed_started = time.perf_counter()
    vectors = await embedder.embed_texts([c["content"] for c in chunks])
    summary.chunks_embedded = len(vectors)
    logger.info("Embedded %d chunks in %.1fs", len(vectors), time.perf_counter() - embed_started)

    by_document: dict[str, list[Document]] = {}
    for chunk, vector in zip(chunks, vectors, strict=True):
        by_document.setdefault(chunk["document_id"], []).append(
            Document(
                content=chunk["content"],
                source=chunk["source"],
                date=chunk.get("date"),
                topic=chunk.get("topic"),
                authority=chunk.get("authority"),
                section=chunk.get("section"),
                document_id=chunk["document_id"],
                age_min_months=chunk.get("age_min_months", 0),
                age_max_months=chunk.get("age_max_months", 60),
                chunk_index=chunk["chunk_index"],
                content_hash=chunk.get("content_hash"),
                embedding=vector,
            )
        )

    for doc_id, doc_chunks in by_document.items():
        written = await store.upsert(doc_chunks, document_id=doc_id)
        summary.chunks_upserted += written
        logger.info("upserted   %s: %d chunks", doc_id, written)

    summary.elapsed_seconds = time.perf_counter() - started
    _log_summary(summary)
    return summary


def _log_summary(summary: IngestionSummary) -> None:
    logger.info("=" * 60)
    logger.info("Ingestion complete in %.1fs", summary.elapsed_seconds)
    logger.info("  documents loaded:   %d", summary.loaded)
    logger.info("  unchanged:          %d", summary.unchanged)
    logger.info("  new:                %d", summary.new)
    logger.info("  changed:            %d", summary.changed)
    logger.info("  chunks embedded:    %d", summary.chunks_embedded)
    logger.info("  chunks upserted:    %d", summary.chunks_upserted)
    if summary.stale_document_ids:
        logger.info("  stale in store:     %s", ", ".join(summary.stale_document_ids))
    logger.info("=" * 60)
