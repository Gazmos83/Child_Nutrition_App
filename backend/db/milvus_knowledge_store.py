"""Milvus Lite implementation of the knowledge store (Day 3 design.md Decisions 4-5).

- Explicit typed schema; deterministic chunk ids so re-ingestion is idempotent.
- FLAT index with COSINE metric: exact search, deterministic ranking, scores usable as a
  relevance floor. The corpus is ~1-2k vectors, so ANN buys nothing here.
- Collection *properties* record the embedding model and dimension it was built with
  (Milvus Lite does not persist the schema description); opening it with a different
  configured model is an error, not a silent mismatch.
- Filter expressions are rendered only from a validated ``SearchFilter``. No method
  accepts a raw expression string.

``MilvusClient`` is synchronous; calls are pushed to a worker thread so the event loop
stays free during streaming responses.
"""

import asyncio
import hashlib
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pymilvus import DataType, MilvusClient

from backend.db.knowledge_store import (
    MAX_AGE_MONTHS,
    MIN_AGE_MONTHS,
    Document,
    Embedder,
    KnowledgeStore,
    SearchFilter,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "nutrition_knowledge"
REINGEST_HINT = "delete the Milvus database and run `uv run scripts/ingest.py`"

_OUTPUT_FIELDS = [
    "content",
    "document_id",
    "source",
    "year",
    "topic",
    "authority",
    "section",
    "age_min_months",
    "age_max_months",
    "chunk_index",
    "content_hash",
]


def chunk_id(document_id: str, chunk_index: int) -> str:
    """Deterministic primary key for a chunk: same document + position -> same id."""
    return hashlib.sha256(f"{document_id}:{chunk_index}".encode()).hexdigest()[:32]


def render_filter(filter: SearchFilter | None) -> str:
    """Render a validated filter to a Milvus boolean expression.

    Only validated integers and ``Authority`` literals are interpolated (Decision 5).
    """
    if filter is None or filter.is_empty:
        return ""
    parts: list[str] = []
    if filter.has_age:
        # Interval overlap: passage range [lo, hi] intersects requested [min, max].
        parts.append(
            f"age_min_months <= {int(filter.age_max_months)} and "
            f"age_max_months >= {int(filter.age_min_months)}"
        )
    if filter.authorities:
        values = ", ".join(json.dumps(a) for a in filter.authorities)
        parts.append(f"authority in [{values}]")
    return " and ".join(parts)


# Property keys stamped on the collection at creation time.
PROP_EMBEDDING_MODEL = "kb.embedding_model"
PROP_DIMENSION = "kb.dimension"


def _str(value: str | None) -> str:
    return value or ""


class MilvusKnowledgeStore(KnowledgeStore):
    """Milvus Lite in-process knowledge store."""

    def __init__(self, db_path: str, embedder: Embedder) -> None:
        """Open (lazily) the Milvus Lite database at ``db_path``.

        Nothing is touched until the first call: the app must boot with no vector store.
        """
        self.db_path = db_path
        self.embedder = embedder
        self._client: MilvusClient | None = None
        self._collection_ready = False
        self._lock = threading.Lock()

    # -- connection & schema ---------------------------------------------------------

    def _connect(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(self.db_path)
            logger.info("Milvus Lite opened at %s", self.db_path)
        return self._client

    def _check_existing_collection(self, client: MilvusClient) -> None:
        props = client.describe_collection(COLLECTION_NAME).get("properties") or {}
        built_model = props.get(PROP_EMBEDDING_MODEL)
        if built_model and built_model != self.embedder.model_name:
            raise RuntimeError(
                f"Collection {COLLECTION_NAME!r} was built with embedding model "
                f"{built_model!r} but EMBEDDING_MODEL is {self.embedder.model_name!r}. "
                f"Vectors from different models are not comparable; {REINGEST_HINT}."
            )
        built_dim = int(props.get(PROP_DIMENSION) or 0)
        if built_dim and self.embedder.dimension and built_dim != self.embedder.dimension:
            raise RuntimeError(
                f"Collection {COLLECTION_NAME!r} has {built_dim}-dimension vectors but "
                f"{self.embedder.model_name!r} produces {self.embedder.dimension}; "
                f"{REINGEST_HINT}."
            )

    def _create_collection(self, client: MilvusClient, dimension: int) -> None:
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("content", DataType.VARCHAR, max_length=8192)
        schema.add_field("document_id", DataType.VARCHAR, max_length=256)
        schema.add_field("source", DataType.VARCHAR, max_length=512)
        schema.add_field("year", DataType.INT64)
        schema.add_field("topic", DataType.VARCHAR, max_length=256)
        schema.add_field("authority", DataType.VARCHAR, max_length=64)
        schema.add_field("section", DataType.VARCHAR, max_length=512)
        schema.add_field("age_min_months", DataType.INT64)
        schema.add_field("age_max_months", DataType.INT64)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("content_hash", DataType.VARCHAR, max_length=64)

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="FLAT", metric_type="COSINE")
        client.create_collection(COLLECTION_NAME, schema=schema, index_params=index_params)
        client.alter_collection_properties(
            COLLECTION_NAME,
            properties={
                PROP_EMBEDDING_MODEL: self.embedder.model_name,
                PROP_DIMENSION: str(dimension),
            },
        )
        logger.info(
            "Created collection %s (model=%s, dim=%d, FLAT/COSINE)",
            COLLECTION_NAME,
            self.embedder.model_name,
            dimension,
        )

    def _ensure_collection(
        self, dimension: int | None = None, create: bool = False
    ) -> MilvusClient:
        """Open the client and validate (or create) the collection. Thread-safe."""
        with self._lock:
            client = self._connect()
            if self._collection_ready:
                return client
            if client.has_collection(COLLECTION_NAME):
                self._check_existing_collection(client)
            elif create:
                dim = dimension or self.embedder.dimension
                if not dim:
                    raise RuntimeError(
                        "Cannot create the collection: embedding dimension is unknown. "
                        "Embed at least one text first."
                    )
                self._create_collection(client, dim)
            else:
                raise RuntimeError(
                    f"Knowledge base collection {COLLECTION_NAME!r} does not exist in "
                    f"{self.db_path}; run `uv run scripts/ingest.py` first."
                )
            client.load_collection(COLLECTION_NAME)
            self._collection_ready = True
            return client

    async def _run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    def close(self) -> None:
        """Release the Milvus Lite handle (tests; process shutdown)."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None
                self._collection_ready = False

    # -- reads -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter: SearchFilter | None = None,
    ) -> list[Document]:
        """Embed ``query`` with the configured model and return the top-K passages."""
        if not query.strip():
            return []
        await self._run(self._ensure_collection)
        vector = await self.embedder.embed_query(query)
        return await self.search_by_embedding(vector, top_k=top_k, filter=filter)

    async def search_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter: SearchFilter | None = None,
    ) -> list[Document]:
        """Search with an already-computed vector."""
        client = await self._run(self._ensure_collection)
        expr = render_filter(filter)
        try:
            results = await self._run(
                client.search,
                collection_name=COLLECTION_NAME,
                data=[query_embedding],
                limit=top_k,
                filter=expr,
                output_fields=_OUTPUT_FIELDS,
                search_params={"metric_type": "COSINE"},
            )
        except Exception as exc:
            raise RuntimeError(f"Knowledge store search failed: {exc}") from exc

        documents: list[Document] = []
        for hit in results[0] if results else []:
            entity = hit.get("entity", {})
            documents.append(
                Document(
                    content=entity.get("content", ""),
                    source=entity.get("source") or "unknown",
                    date=entity.get("year") or None,
                    topic=entity.get("topic") or None,
                    authority=entity.get("authority") or None,
                    section=entity.get("section") or None,
                    document_id=entity.get("document_id") or None,
                    age_min_months=entity.get("age_min_months", MIN_AGE_MONTHS),
                    age_max_months=entity.get("age_max_months", MAX_AGE_MONTHS),
                    chunk_index=entity.get("chunk_index", 0),
                    content_hash=entity.get("content_hash") or None,
                    # COSINE metric: Milvus reports similarity, higher is closer.
                    score=float(hit.get("distance", 0.0)),
                )
            )
        return documents

    async def count(self) -> int:
        """Number of chunks in the collection (0 if it does not exist yet)."""
        try:
            client = await self._run(self._ensure_collection)
        except RuntimeError:
            return 0
        stats = await self._run(client.get_collection_stats, COLLECTION_NAME)
        return int(stats.get("row_count", 0))

    async def list_document_hashes(self) -> dict[str, str]:
        """``{document_id: content_hash}`` for every indexed document."""
        try:
            client = await self._run(self._ensure_collection)
        except RuntimeError:
            return {}
        rows = await self._run(
            client.query,
            collection_name=COLLECTION_NAME,
            filter="chunk_index == 0",
            output_fields=["document_id", "content_hash"],
        )
        return {row["document_id"]: row["content_hash"] for row in rows if row.get("document_id")}

    # -- writes ------------------------------------------------------------------------

    @staticmethod
    def _row(doc: Document, document_id: str) -> dict[str, Any]:
        return {
            "id": chunk_id(document_id, doc.chunk_index),
            "embedding": doc.embedding,
            "content": doc.content,
            "document_id": document_id,
            "source": _str(doc.source),
            "year": int(doc.date or 0),
            "topic": _str(doc.topic),
            "authority": _str(doc.authority),
            "section": _str(doc.section),
            "age_min_months": int(doc.age_min_months),
            "age_max_months": int(doc.age_max_months),
            "chunk_index": int(doc.chunk_index),
            "content_hash": _str(doc.content_hash),
        }

    async def upsert(self, documents: list[Document], document_id: str | None = None) -> int:
        """Replace each affected document's chunks atomically-enough: delete then insert."""
        if not documents:
            return 0

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for i, doc in enumerate(documents):
            if doc.embedding is None:
                raise ValueError(f"Document {i} has no embedding; embed before upsert.")
            doc_id = document_id or doc.document_id
            if not doc_id:
                raise ValueError(f"Document {i} has no document_id.")
            grouped[doc_id].append(self._row(doc, doc_id))

        dimension = len(documents[0].embedding)  # type: ignore[arg-type]
        client = await self._run(self._ensure_collection, dimension, True)

        def _write() -> int:
            written = 0
            for doc_id, rows in grouped.items():
                client.delete(COLLECTION_NAME, filter=f"document_id == {json.dumps(doc_id)}")
                client.insert(COLLECTION_NAME, data=rows)
                written += len(rows)
            client.flush(COLLECTION_NAME)
            return written

        try:
            written = await self._run(_write)
        except Exception as exc:
            raise RuntimeError(f"Knowledge store upsert failed: {exc}") from exc
        logger.info("Upserted %d chunks across %d documents", written, len(grouped))
        return written

    async def delete(self, document_id: str) -> int:
        """Delete every chunk of ``document_id``; returns the number removed."""
        try:
            client = await self._run(self._ensure_collection)
        except RuntimeError:
            return 0
        expr = f"document_id == {json.dumps(document_id)}"
        try:
            existing = await self._run(
                client.query, collection_name=COLLECTION_NAME, filter=expr, output_fields=["id"]
            )
            if existing:
                await self._run(client.delete, COLLECTION_NAME, filter=expr)
                await self._run(client.flush, COLLECTION_NAME)
        except Exception as exc:
            raise RuntimeError(f"Knowledge store delete failed: {exc}") from exc
        logger.info("Deleted %d chunks of %s", len(existing), document_id)
        return len(existing)
