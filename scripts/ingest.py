#!/usr/bin/env python
"""Re-runnable knowledge base ingestion.

Loads the Markdown corpus and manifest, embeds only documents that are new or changed
since the last run, and replaces their chunks in Milvus Lite. Safe to run repeatedly.

Usage:
    uv run scripts/ingest.py

Configuration (see .env.example): OPENROUTER_API_KEY (required), EMBEDDING_MODEL,
MILVUS_DB_PATH, CORPUS_DIR.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.config import get_rag_settings  # noqa: E402
from backend.db.milvus_knowledge_store import MilvusKnowledgeStore  # noqa: E402
from backend.knowledge.embeddings import EmbeddingProvider  # noqa: E402
from backend.knowledge.ingestion import run_ingestion  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")


async def main() -> int:
    settings = get_rag_settings()
    if not Path(settings.corpus_dir).exists():
        logger.error("Corpus directory not found: %s (set CORPUS_DIR)", settings.corpus_dir)
        return 1
    try:
        embedder = EmbeddingProvider.from_settings(settings)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    store = MilvusKnowledgeStore(settings.milvus_db_path, embedder)
    logger.info("Milvus Lite database: %s", settings.milvus_db_path)
    try:
        summary = await run_ingestion(settings.corpus_dir, store, embedder)
        total = await store.count()
        logger.info("Collection now holds %d chunks", total)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("Ingestion failed: %s", exc)
        return 1
    finally:
        store.close()
    return 0 if summary.loaded else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
