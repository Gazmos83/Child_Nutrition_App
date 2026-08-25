"""Chunk documents for embedding and retrieval."""

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def chunk_documents(documents: list[dict], chunk_size: int = 512, chunk_overlap: int = 50) -> list[dict]:
    """Split documents into chunks for embedding.

    Args:
        documents: List of dicts with 'content', 'source', etc.
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of dicts with 'content', 'source', 'topic', and chunk-specific fields.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in documents:
        content = doc.get("content", "")
        if not content:
            logger.warning(f"Document {doc.get('source')} has empty content; skipping")
            continue

        split_texts = splitter.split_text(content)
        for i, chunk_text in enumerate(split_texts):
            chunks.append({
                "content": chunk_text,
                "source": doc.get("source", "unknown"),
                "topic": doc.get("topic"),
                "authority": doc.get("authority"),
                "date": doc.get("date"),
                "page_ref": doc.get("page_ref"),
                "document_id": doc.get("document_id", doc.get("source")),
                "chunk_index": i,
                "total_chunks": len(split_texts),
            })

        logger.debug(f"Split {doc.get('source')} into {len(split_texts)} chunks")

    logger.info(f"Chunked {len(documents)} documents into {len(chunks)} chunks")
    return chunks
