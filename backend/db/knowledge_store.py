"""Abstract interface for retrieving documents from a knowledge base.

The retriever (Day 3+) calls through this interface, not directly against Milvus,
so implementations can swap without touching retrieval logic. Day 2: Milvus Lite.
Day 7+: Milvus Standalone / Zilliz.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Document:
    """A knowledge base document chunk with embeddings and metadata."""

    content: str
    """The chunk text."""

    source: str
    """Publication source (e.g., 'WHO Child Growth Standards 2006')."""

    date: int | None = None
    """Publication year, if available."""

    topic: str | None = None
    """Topic or section (e.g., 'complementary feeding', 'iron requirements')."""

    authority: str | None = None
    """Authority level (e.g., 'WHO official', 'national guideline')."""

    page_ref: str | None = None
    """Page or section reference from the original document."""

    document_id: str | None = None
    """Unique identifier for the source document (for deduplication during ingestion)."""

    score: float | None = None
    """Relevance score returned by the retriever (0-1, higher is more relevant)."""


class KnowledgeStore(ABC):
    """Abstract base for knowledge base implementations."""

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[Document]:
        """Retrieve documents most similar to the query.

        Args:
            query: Natural language query.
            top_k: Maximum number of results to return.

        Returns:
            List of Document objects, ordered by relevance (highest first).

        Raises:
            RuntimeError: if the knowledge store is not available or configured.
        """
        ...

    @abstractmethod
    async def upsert(
        self, documents: list[Document], document_id: str | None = None
    ) -> int:
        """Insert or update documents in the knowledge base.

        If documents share a document_id, and that ID already exists in the collection,
        the old documents are replaced with the new ones atomically.

        Args:
            documents: List of Document chunks to index.
            document_id: If provided, all documents are tagged with this ID. Otherwise,
                         each document must have its own document_id set.

        Returns:
            Count of documents inserted/updated.

        Raises:
            RuntimeError: if the upsert fails.
        """
        ...

    @abstractmethod
    async def delete(self, document_id: str) -> int:
        """Remove all documents with the given ID.

        Args:
            document_id: The document ID to delete.

        Returns:
            Count of documents deleted.

        Raises:
            RuntimeError: if the delete fails.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of documents in the store.

        Returns:
            Document count.
        """
        ...
