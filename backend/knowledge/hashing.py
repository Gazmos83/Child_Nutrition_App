"""Content hashing for change detection during ingestion."""

import hashlib
import logging

logger = logging.getLogger(__name__)


def content_hash(text: str) -> str:
    """Compute a SHA256 hash of document content for change detection.

    Args:
        text: Document content.

    Returns:
        Hex digest of the SHA256 hash.
    """
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_documents(documents: list[dict]) -> dict[str, str]:
    """Compute hashes for a set of documents.

    Returns a dict mapping document_id -> content_hash.

    Args:
        documents: List of dicts with 'content' and 'document_id' keys.

    Returns:
        Dict of {document_id: hash}.
    """
    hashes = {}
    for doc in documents:
        doc_id = doc.get("document_id", doc.get("source", "unknown"))
        content = doc.get("content", "")
        hashes[doc_id] = content_hash(content)
    return hashes
