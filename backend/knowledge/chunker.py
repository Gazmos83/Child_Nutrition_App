"""Chunk documents for embedding and retrieval.

Splits on Markdown headings first, then paragraphs, so a chunk rarely straddles two
sections; each chunk records the nearest preceding ``##`` heading as its ``section`` so
citations can point at a part of a document (Day 3 task 4.1).
"""

import logging
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# Metadata copied from a document onto every one of its chunks.
_CARRIED_KEYS = (
    "source",
    "topic",
    "authority",
    "date",
    "document_id",
    "age_min_months",
    "age_max_months",
    "content_hash",
    "url",
)


def _headings(text: str) -> list[tuple[int, str]]:
    """(offset, heading text) for every ``##``+ heading; the ``#`` title is excluded."""
    return [(m.start(), m.group(2)) for m in _HEADING.finditer(text) if len(m.group(1)) >= 2]


def _section_at(headings: list[tuple[int, str]], start: int, end: int) -> str | None:
    """The last heading at or before ``start``; failing that (a chunk that opens with the
    document title), the first heading inside the chunk itself."""
    current = None
    for offset, title in headings:
        if offset <= start:
            current = title
        else:
            break
    if current is None:
        for offset, title in headings:
            if start < offset < end:
                return title
    return current


def chunk_documents(
    documents: list[dict], chunk_size: int = 512, chunk_overlap: int = 50
) -> list[dict]:
    """Split documents into chunks for embedding.

    Args:
        documents: Dicts with ``content`` plus source metadata (see loaders.load_corpus).
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        Dicts carrying the chunk ``content``, the document's metadata, ``section``,
        ``chunk_index`` and ``total_chunks``.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
        length_function=len,
        add_start_index=True,
    )

    chunks: list[dict] = []
    for doc in documents:
        content = doc.get("content", "")
        if not content:
            logger.warning("Document %s has empty content; skipping", doc.get("source"))
            continue

        headings = _headings(content)
        pieces = splitter.create_documents([content])
        carried = {key: doc.get(key) for key in _CARRIED_KEYS if key in doc}
        carried.setdefault("document_id", doc.get("source"))
        carried.setdefault("source", "unknown")

        for i, piece in enumerate(pieces):
            start = piece.metadata.get("start_index", 0)
            chunks.append(
                {
                    "content": piece.page_content.strip(),
                    **carried,
                    "section": _section_at(headings, start, start + len(piece.page_content))
                    or doc.get("section"),
                    "chunk_index": i,
                    "total_chunks": len(pieces),
                }
            )
        logger.debug("Split %s into %d chunks", doc.get("source"), len(pieces))

    logger.info("Chunked %d documents into %d chunks", len(documents), len(chunks))
    return chunks
