"""Milvus Lite implementation of the knowledge store."""

import logging
from typing import TYPE_CHECKING

from pymilvus import Collection, MilvusClient, connections

from backend.db.knowledge_store import Document, KnowledgeStore
from backend.core.config import get_settings

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_NAME = "nutrition_knowledge"
VECTOR_DIM = 384  # all-MiniLM-L6-v2 and OpenAI text-embedding-3-small both use 384


class MilvusKnowledgeStore(KnowledgeStore):
    """Milvus Lite in-process knowledge store.

    Connects to a local Milvus Lite instance persisting to a file (milvus.db).
    """

    def __init__(self, db_path: str = "milvus.db") -> None:
        """Initialize the Milvus client and collection.

        Args:
            db_path: Path to the Milvus Lite database file.
        """
        self.db_path = db_path
        self.client = MilvusClient(db_path)
        logger.info(f"Milvus Lite initialized at {db_path}")

    async def search(self, query: str, top_k: int = 5) -> list[Document]:
        """Search for documents similar to the query.

        Args:
            query: The query text (will be embedded by the caller before this is called,
                   or we embed it here; for now, assume the caller embeds it).
            top_k: Maximum results.

        Returns:
            List of Documents.

        Raises:
            RuntimeError: if Milvus is not available.
        """
        raise NotImplementedError(
            "search() requires a query embedding. Use the retriever (Day 3+) "
            "which handles embedding."
        )

    async def search_by_embedding(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[Document]:
        """Search by an already-computed embedding vector.

        Args:
            query_embedding: The embedding vector for the query.
            top_k: Maximum results.

        Returns:
            List of Documents, ordered by relevance.
        """
        try:
            # Milvus search returns results as a list of lists, each inner list
            # is [distance, primary_key_value] for a hit.
            results = self.client.search(
                collection_name=COLLECTION_NAME,
                data=[query_embedding],
                limit=top_k,
                output_fields=["content", "source", "date", "topic", "authority", "page_ref", "document_id"],
            )

            documents = []
            for hit_group in results:
                for hit in hit_group:
                    # hit is a dict-like object with fields from output_fields + distance/id
                    doc = Document(
                        content=hit.get("content", ""),
                        source=hit.get("source", "unknown"),
                        date=hit.get("date"),
                        topic=hit.get("topic"),
                        authority=hit.get("authority"),
                        page_ref=hit.get("page_ref"),
                        document_id=hit.get("document_id"),
                        score=1 - hit.get("distance", 0),  # Convert distance to similarity
                    )
                    documents.append(doc)

            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise RuntimeError(f"Knowledge store search failed: {e}") from e

    async def upsert(
        self, documents: list[Document], document_id: str | None = None
    ) -> int:
        """Upsert documents into the collection.

        Args:
            documents: List of Documents to insert/update.
            document_id: If set, all documents are tagged with this ID.

        Returns:
            Count of documents upserted.
        """
        if not documents:
            return 0

        # Prepare data for Milvus. For now, assume embeddings are already in documents
        # (Day 3's ingestion pipeline will compute them). If not present, raise an error.
        rows = []
        for i, doc in enumerate(documents):
            if not hasattr(doc, "embedding") or doc.embedding is None:
                raise ValueError(
                    f"Document {i} has no embedding. Ingestion must compute embeddings before upsert."
                )

            rows.append({
                "id": hash(f"{doc.document_id or doc.source}_{i}") % (2 ** 31),
                "embedding": doc.embedding,
                "content": doc.content,
                "source": doc.source,
                "date": doc.date,
                "topic": doc.topic,
                "authority": doc.authority,
                "page_ref": doc.page_ref,
                "document_id": doc.document_id,
            })

        try:
            result = self.client.insert(
                collection_name=COLLECTION_NAME,
                data=rows,
            )
            logger.info(f"Upserted {len(documents)} documents")
            return len(documents)
        except Exception as e:
            logger.error(f"Upsert failed: {e}")
            raise RuntimeError(f"Knowledge store upsert failed: {e}") from e

    async def delete(self, document_id: str) -> int:
        """Delete all documents with the given ID.

        Args:
            document_id: The document ID to delete.

        Returns:
            Count of documents deleted.
        """
        try:
            # Milvus delete uses filter expressions
            result = self.client.delete(
                collection_name=COLLECTION_NAME,
                filter=f'document_id == "{document_id}"',
            )
            logger.info(f"Deleted documents with ID {document_id}")
            return result.get("delete_count", 0) if result else 0
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            raise RuntimeError(f"Knowledge store delete failed: {e}") from e

    async def count(self) -> int:
        """Return the total document count.

        Returns:
            Document count.
        """
        try:
            num_entities = self.client.num_entities(collection_name=COLLECTION_NAME)
            return num_entities
        except Exception as e:
            logger.warning(f"Failed to count documents: {e}")
            return 0
