"""Abstract interface for retrieving documents from a knowledge base.

The retriever (Day 3+) calls through this interface, not directly against Milvus,
so implementations can swap without touching retrieval logic. Day 2: Milvus Lite.
Day 7+: Milvus Standalone / Zilliz.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Controlled vocabulary for the ``authority`` metadata field. Matches the values allowed
# in knowledge-base/manifest.yaml; the authority search filter is typed against it so
# free text can never reach a vector-store filter expression (hard rules 6 and 7).
Authority = Literal["WHO", "AAP", "CDC", "USDA/HHS", "NIH", "FDA/EPA"]
AUTHORITIES: tuple[str, ...] = get_args(Authority)

# The supported age range, in months (hard rule 1). Mirrors ChildProfile.age_in_months.
MIN_AGE_MONTHS = 0
MAX_AGE_MONTHS = 60


@dataclass
class Document:
    """A knowledge base document chunk with metadata (and, during ingestion, its vector)."""

    content: str
    """The chunk text."""

    source: str
    """Publication source (e.g., 'WHO Child Growth Standards 2006')."""

    date: int | None = None
    """Publication year, if available."""

    topic: str | None = None
    """Topic or section (e.g., 'complementary feeding', 'iron requirements')."""

    authority: str | None = None
    """Authority level (e.g., 'WHO', 'AAP')."""

    section: str | None = None
    """Section heading or page reference within the original document."""

    document_id: str | None = None
    """Unique identifier for the source document (for deduplication during ingestion)."""

    age_min_months: int = MIN_AGE_MONTHS
    """Youngest age, in months, the source document applies to."""

    age_max_months: int = MAX_AGE_MONTHS
    """Oldest age, in months, the source document applies to."""

    chunk_index: int = 0
    """Position of this chunk within its document."""

    content_hash: str | None = None
    """Hash of the whole source document's content, for change detection."""

    score: float | None = None
    """Relevance score returned by the retriever (cosine similarity; higher is better)."""

    embedding: list[float] | None = field(default=None, repr=False)
    """Vector, populated during ingestion. Never returned from search."""


class SearchFilter(BaseModel):
    """Validated metadata filter for :meth:`KnowledgeStore.search`.

    Every value is an integer within 0-60 months or a member of the ``Authority``
    vocabulary. Stores render Milvus expressions from these fields only -- user text
    never reaches the expression string (Day 3 design.md Decision 5).

    Age semantics are *overlap*: a passage matches when its applicable range intersects
    ``[age_min_months, age_max_months]``. Supplying a single bound filters for that
    exact age.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    age_min_months: int | None = Field(default=None, ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)
    age_max_months: int | None = Field(default=None, ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)
    authorities: tuple[Authority, ...] = ()

    @model_validator(mode="after")
    def _complete_and_order_age_bounds(self) -> SearchFilter:
        lo, hi = self.age_min_months, self.age_max_months
        if lo is None and hi is not None:
            object.__setattr__(self, "age_min_months", hi)
        elif hi is None and lo is not None:
            object.__setattr__(self, "age_max_months", lo)
        elif lo is not None and hi is not None and lo > hi:
            raise ValueError(f"age_min_months ({lo}) must not exceed age_max_months ({hi})")
        return self

    @property
    def has_age(self) -> bool:
        return self.age_min_months is not None

    @property
    def is_empty(self) -> bool:
        return not self.has_age and not self.authorities

    def without_age(self) -> SearchFilter:
        """The same filter with the age constraint removed (advanced-RAG fallback)."""
        return SearchFilter(authorities=self.authorities)


class Embedder(Protocol):
    """What a knowledge store needs from an embedding provider."""

    model_name: str

    @property
    def dimension(self) -> int | None: ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


class KnowledgeStore(ABC):
    """Abstract base for knowledge base implementations."""

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter: SearchFilter | None = None,
    ) -> list[Document]:
        """Retrieve documents most similar to the query.

        Args:
            query: Natural language query. The store embeds it.
            top_k: Maximum number of results to return.
            filter: Optional validated metadata filter.

        Returns:
            List of Document objects, ordered by relevance (highest first), each with
            ``score`` set.

        Raises:
            RuntimeError: if the knowledge store is not available or configured.
        """
        ...

    @abstractmethod
    async def upsert(self, documents: list[Document], document_id: str | None = None) -> int:
        """Insert or update documents in the knowledge base.

        All existing chunks for each affected ``document_id`` are removed first, so a
        document is replaced as a whole and never left as a mix of old and new chunks.

        Args:
            documents: List of Document chunks to index, with ``embedding`` set.
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
        """Return the total number of chunks in the store."""
        ...

    @abstractmethod
    async def list_document_hashes(self) -> dict[str, str]:
        """Return ``{document_id: content_hash}`` for every indexed document.

        Used by ingestion to decide which documents are new or changed.
        """
        ...
