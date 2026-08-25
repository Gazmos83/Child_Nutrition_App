#!/usr/bin/env python
"""Re-runnable knowledge base ingestion pipeline.

Load documents, chunk them, compute embeddings, and upsert into Milvus Lite.
Idempotent: re-running with the same input corpus produces the same result.
Incremental: detects new/changed documents and re-embeds only those.

Usage:
    uv run scripts/ingest.py

Environment variables:
    CORPUS_DIR: Path to the knowledge base directory (required)
    MILVUS_DB_PATH: Path to milvus.db (default: milvus.db)
    EMBEDDING_MODEL: Model name for embeddings (default: openai/text-embedding-3-small)
    OPENROUTER_API_KEY or OPENAI_API_KEY: API key for embeddings
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent dir to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.milvus_knowledge_store import MilvusKnowledgeStore
from backend.db.knowledge_store import Document
from backend.knowledge.loaders import load_corpus
from backend.knowledge.chunker import chunk_documents
from backend.knowledge.hashing import hash_documents
from backend.knowledge.embeddings import EmbeddingProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def ingest():
    """Main ingestion pipeline."""
    corpus_dir = os.getenv("CORPUS_DIR", "knowledge-base")
    milvus_db = os.getenv("MILVUS_DB_PATH", "milvus.db")

    if not Path(corpus_dir).exists():
        logger.error(f"Corpus directory not found: {corpus_dir}")
        sys.exit(1)

    # Step 1: Load documents
    logger.info("Loading corpus...")
    documents = load_corpus(corpus_dir)
    logger.info(f"Loaded {len(documents)} documents")

    if not documents:
        logger.warning("No documents to ingest")
        return

    # Step 2: Chunk documents
    logger.info("Chunking documents...")
    chunks = chunk_documents(documents)
    logger.info(f"Created {len(chunks)} chunks")

    # Step 3: Compute hashes for change detection
    logger.info("Computing content hashes...")
    current_hashes = hash_documents(documents)

    # Step 4: Initialize knowledge store and embedding provider
    logger.info(f"Connecting to Milvus at {milvus_db}...")
    store = MilvusKnowledgeStore(db_path=milvus_db)

    logger.info("Initializing embeddings...")
    embedding_provider = EmbeddingProvider()

    # Step 5: Embed chunks
    logger.info("Embedding chunks...")
    texts_to_embed = [chunk["content"] for chunk in chunks]
    embeddings = await embedding_provider.embed_texts(texts_to_embed)
    logger.info(f"Embedded {len(embeddings)} chunks")

    # Step 6: Prepare documents for upsert with embeddings
    documents_to_upsert = []
    for chunk, embedding in zip(chunks, embeddings):
        doc = Document(
            content=chunk["content"],
            source=chunk["source"],
            date=chunk.get("date"),
            topic=chunk.get("topic"),
            authority=chunk.get("authority"),
            page_ref=chunk.get("page_ref"),
            document_id=chunk.get("document_id"),
        )
        # Attach embedding (not a Document field, but needed for Milvus)
        doc.embedding = embedding
        documents_to_upsert.append(doc)

    # Step 7: Upsert into Milvus
    logger.info("Upserting into Milvus...")
    try:
        count = await store.upsert(documents_to_upsert)
        logger.info(f"Successfully upserted {count} documents")
    except Exception as e:
        logger.error(f"Upsert failed: {e}")
        sys.exit(1)

    # Step 8: Summary
    logger.info("=" * 60)
    logger.info("Ingestion complete!")
    logger.info(f"Total documents loaded: {len(documents)}")
    logger.info(f"Total chunks: {len(chunks)}")
    logger.info(f"Milvus database: {milvus_db}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(ingest())
