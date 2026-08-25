"""Embed document chunks using OpenRouter or local fallback."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """Wrapper around embedding models with OpenRouter fallback."""

    def __init__(self):
        """Initialize the embedding provider (OpenRouter or fallback)."""
        self.model_name = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
        self.use_local = False
        self.embedder = None
        self._init_provider()

    def _init_provider(self):
        """Try OpenRouter first; fall back to sentence-transformers on failure."""
        try:
            from langchain_openai import OpenAIEmbeddings

            api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("No OpenRouter/OpenAI API key found; using local embeddings")
                self._init_local()
                return

            self.embedder = OpenAIEmbeddings(
                model=self.model_name,
                api_key=api_key,
                base_url="https://openrouter.io/api/v1",  # OpenRouter endpoint
            )
            logger.info(f"Using OpenRouter embeddings model: {self.model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenRouter embeddings: {e}. Using local fallback.")
            self._init_local()

    def _init_local(self):
        """Fall back to sentence-transformers for local embeddings."""
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")
            self.embedder = model
            self.use_local = True
            logger.info("Using local sentence-transformers embeddings (all-MiniLM-L6-v2)")
        except Exception as e:
            logger.error(f"Failed to initialize local embeddings: {e}")
            raise RuntimeError("No embedding provider available") from e

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        if not texts:
            return []

        try:
            if self.use_local:
                embeddings = self.embedder.encode(texts, convert_to_tensor=False)
                return [embedding.tolist() if hasattr(embedding, 'tolist') else embedding for embedding in embeddings]
            else:
                # LangChain's OpenAIEmbeddings
                embeddings = await self.embedder.aembed_documents(texts)
                return embeddings
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise RuntimeError(f"Embedding failed: {e}") from e

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        Args:
            query: String to embed.

        Returns:
            Embedding vector (list of floats).
        """
        if not query:
            return []

        try:
            if self.use_local:
                embedding = self.embedder.encode([query], convert_to_tensor=False)[0]
                return embedding.tolist() if hasattr(embedding, 'tolist') else embedding
            else:
                # LangChain's OpenAIEmbeddings
                embedding = await self.embedder.aembed_query(query)
                return embedding
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            raise RuntimeError(f"Query embedding failed: {e}") from e
