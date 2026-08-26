"""Embeddings via OpenRouter -- one explicit model, no fallback.

Day 3 design.md Decision 3. A silent fallback to a different model is a correctness bug,
not resilience: vectors from two models in one collection are incomparable, and the
failure surfaces as "retrieval is mysteriously bad" rather than as an error. So this
module does exactly one thing with exactly one configured model, and fails loudly when it
cannot.

Nothing here touches the network at import time or at construction time; the first
request does.
"""

import logging

from langchain_openai import OpenAIEmbeddings

from backend.core.config import OPENROUTER_BASE_URL, RAGSettings

logger = logging.getLogger(__name__)

# Output dimensions of the embedding models we know about. Used to create the Milvus
# collection before the first vector exists; unknown models are measured from their
# first embedding instead.
KNOWN_DIMENSIONS: dict[str, int] = {
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "openai/text-embedding-ada-002": 1536,
}

# Per-request batch size. OpenRouter proxies to providers with their own input limits;
# 64 chunks of <=512 characters stays comfortably inside all of them.
_BATCH_SIZE = 64

MISSING_KEY_MESSAGE = (
    "OPENROUTER_API_KEY is not set. Embeddings are served by OpenRouter; add the key to "
    ".env (see .env.example) and retry."
)


class EmbeddingProvider:
    """Embed texts and queries with a single OpenRouter-served model."""

    def __init__(
        self,
        model: str,
        api_key: str | None,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        """Configure the provider.

        Args:
            model: OpenRouter embedding model id (e.g. ``openai/text-embedding-3-small``).
            api_key: OpenRouter API key.
            base_url: OpenAI-compatible endpoint; defaults to OpenRouter.

        Raises:
            RuntimeError: if ``api_key`` is missing. Named after the setting so the
                operator knows what to fix.
        """
        if not api_key:
            raise RuntimeError(MISSING_KEY_MESSAGE)

        self.model_name = model
        self._dimension: int | None = KNOWN_DIMENSIONS.get(model)
        self._embedder = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
            # OpenRouter accepts strings, not the pre-tokenised input LangChain sends
            # when it thinks it is talking to OpenAI.
            check_embedding_ctx_length=False,
        )
        logger.info("Embedding provider: %s via %s", model, base_url)

    @classmethod
    def from_settings(cls, settings: RAGSettings) -> EmbeddingProvider:
        """Build the provider from :class:`RAGSettings`."""
        return cls(model=settings.embedding_model, api_key=settings.openrouter_api_key)

    @property
    def dimension(self) -> int | None:
        """Vector dimension, if known -- from the table or from the first embedding."""
        return self._dimension

    def _record_dimension(self, vector: list[float]) -> None:
        if self._dimension is None:
            self._dimension = len(vector)
        elif len(vector) != self._dimension:
            raise RuntimeError(
                f"Embedding model {self.model_name!r} returned a {len(vector)}-dimension "
                f"vector but {self._dimension} was expected."
            )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks, preserving order."""
        if not texts:
            return []
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[start : start + _BATCH_SIZE]
                vectors.extend(await self._embedder.aembed_documents(batch))
        except Exception as exc:
            raise RuntimeError(
                f"Embedding failed with model {self.model_name!r} via OpenRouter: {exc}"
            ) from exc
        if vectors:
            self._record_dimension(vectors[0])
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        if not query:
            return []
        try:
            vector = await self._embedder.aembed_query(query)
        except Exception as exc:
            raise RuntimeError(
                f"Query embedding failed with model {self.model_name!r} via OpenRouter: {exc}"
            ) from exc
        self._record_dimension(vector)
        return vector
