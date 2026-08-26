"""Provider wiring: OpenRouter chat model and the process-wide pipeline (Decisions 9, 11).

Nothing here is executed at import time. ``get_pipeline()`` builds embedder -> Milvus
store -> retrievers -> pipeline on first use and caches it for the process.
"""

import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.core.config import OPENROUTER_BASE_URL, RAGSettings, get_rag_settings
from backend.db.milvus_knowledge_store import MilvusKnowledgeStore
from backend.knowledge.embeddings import EmbeddingProvider
from backend.rag.pipeline import RagPipeline
from backend.rag.retrievers import AdvancedRetriever, BasicRetriever

logger = logging.getLogger(__name__)

MISSING_KEY_MESSAGE = (
    "OPENROUTER_API_KEY is not set. The assistant's language model is served by "
    "OpenRouter; add the key to .env (see .env.example)."
)


def build_chat_model(settings: RAGSettings) -> ChatOpenAI:
    """LangChain chat model pointed at OpenRouter's OpenAI-compatible API."""
    if not settings.openrouter_api_key:
        raise RuntimeError(MISSING_KEY_MESSAGE)
    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        timeout=60,
        max_retries=2,
        default_headers={
            # OpenRouter attribution headers (optional, recommended).
            "HTTP-Referer": "https://github.com/child-nutrition-app",
            "X-Title": "Child Nutrition AI App",
        },
    )


def build_pipeline(settings: RAGSettings) -> RagPipeline:
    """Wire the full pipeline from settings. Raises RuntimeError if the key is missing."""
    chat_model = build_chat_model(settings)
    embedder = EmbeddingProvider.from_settings(settings)
    store = MilvusKnowledgeStore(settings.milvus_db_path, embedder)
    logger.info(
        "RAG pipeline: model=%s embeddings=%s milvus=%s floor=%.2f budget=%d",
        settings.openrouter_model,
        settings.embedding_model,
        settings.milvus_db_path,
        settings.rag_min_similarity,
        settings.rag_context_char_budget,
    )
    return RagPipeline(
        retrievers={
            "basic": BasicRetriever(store),
            "advanced": AdvancedRetriever(store, chat_model),
        },
        chat_model=chat_model,
        min_similarity=settings.rag_min_similarity,
        context_char_budget=settings.rag_context_char_budget,
    )


@lru_cache(maxsize=1)
def get_pipeline() -> RagPipeline:
    """Process-wide pipeline, built on first use from the environment."""
    return build_pipeline(get_rag_settings())


def reset_pipeline_cache() -> None:
    """For tests that rebind configuration."""
    get_pipeline.cache_clear()
