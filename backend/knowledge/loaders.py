"""Load documents from the knowledge base corpus using LangChain."""

import logging
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.document_loaders.pdf import PyPDFLoader

logger = logging.getLogger(__name__)


def load_corpus(corpus_dir: str | Path) -> list[dict]:
    """Load all documents from a directory tree.

    Supports Markdown (.md, .txt) and PDF (.pdf) files. Each file's source metadata
    is derived from the filename and directory structure.

    Args:
        corpus_dir: Path to the directory containing documents.

    Returns:
        List of dicts with 'content', 'source', 'path', and 'filename' keys.
    """
    corpus_dir = Path(corpus_dir)
    if not corpus_dir.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    documents = []

    # Load Markdown and text files
    md_loader = DirectoryLoader(
        str(corpus_dir),
        glob="**/*.{md,txt}",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    try:
        md_docs = md_loader.load()
        for doc in md_docs:
            documents.append({
                "content": doc.page_content,
                "source": Path(doc.metadata.get("source", "")).stem,
                "path": doc.metadata.get("source", ""),
                "filename": Path(doc.metadata.get("source", "")).name,
            })
        logger.info(f"Loaded {len(md_docs)} Markdown/text documents")
    except Exception as e:
        logger.warning(f"Failed to load Markdown documents: {e}")

    # Load PDF files
    pdf_loader = DirectoryLoader(
        str(corpus_dir),
        glob="**/*.pdf",
        loader_cls=PyPDFLoader,
    )
    try:
        pdf_docs = pdf_loader.load()
        for doc in pdf_docs:
            documents.append({
                "content": doc.page_content,
                "source": Path(doc.metadata.get("source", "")).stem,
                "path": doc.metadata.get("source", ""),
                "filename": Path(doc.metadata.get("source", "")).name,
                "page": doc.metadata.get("page", None),
            })
        logger.info(f"Loaded {len(pdf_docs)} PDF documents")
    except Exception as e:
        logger.warning(f"Failed to load PDF documents: {e}")

    if not documents:
        logger.warning(f"No documents found in {corpus_dir}")

    return documents
