"""Load the knowledge-base corpus: Markdown/text files plus manifest metadata.

``knowledge-base/manifest.yaml`` is the source of every document's provenance (Day 2
design.md Decision 6; Day 3 knowledge-ingestion-pipeline spec). Files are loaded with
LangChain loaders so the same code path serves Day 3's retriever.
"""

import logging
from pathlib import Path

import yaml
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.document_loaders.pdf import PyPDFLoader
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.db.knowledge_store import MAX_AGE_MONTHS, MIN_AGE_MONTHS, Authority

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.yaml"

# Two passes rather than one "**/*.{md,txt}" glob: the brace form is a shell extension
# that Python's pathlib matcher does not expand, so it silently matched nothing.
_TEXT_GLOBS = ("**/*.md", "**/*.txt")


class ManifestEntry(BaseModel):
    """One document's provenance, as declared in manifest.yaml."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="Path relative to the corpus directory.")
    source: str = Field(min_length=1, description="Citable source title.")
    year: int | None = Field(default=None, ge=1900, le=2100, description="Publication year.")
    topic: str | None = None
    authority: Authority
    age_min_months: int = Field(default=MIN_AGE_MONTHS, ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)
    age_max_months: int = Field(default=MAX_AGE_MONTHS, ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)
    url: str | None = None

    @model_validator(mode="after")
    def _age_bounds_ordered(self) -> ManifestEntry:
        if self.age_min_months > self.age_max_months:
            raise ValueError(
                f"{self.file}: age_min_months ({self.age_min_months}) exceeds "
                f"age_max_months ({self.age_max_months})"
            )
        return self

    @property
    def document_id(self) -> str:
        return document_id_for(self.file)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[ManifestEntry]


def document_id_for(relative_path: str | Path) -> str:
    """Stable document id from a corpus-relative path: ``guidelines/who-iron.md`` ->
    ``guidelines-who-iron``."""
    rel = Path(relative_path)
    return "-".join([*rel.parts[:-1], rel.stem])


def load_manifest(corpus_dir: str | Path) -> dict[str, ManifestEntry]:
    """Read and validate the manifest, keyed by corpus-relative file path.

    A missing manifest is a warning (every document then gets default metadata); an
    invalid one is an error, because silently ingesting with wrong provenance would
    break hard rule 5's citations.
    """
    path = Path(corpus_dir) / MANIFEST_FILENAME
    if not path.exists():
        logger.warning(
            "No %s in %s; documents will carry default metadata", MANIFEST_FILENAME, corpus_dir
        )
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        manifest = Manifest.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"Invalid {path}: {exc}") from exc

    entries: dict[str, ManifestEntry] = {}
    for entry in manifest.documents:
        if entry.file in entries:
            raise ValueError(f"Invalid {path}: {entry.file!r} is listed twice")
        entries[entry.file] = entry
    return entries


def _default_metadata(rel_path: str) -> dict:
    return {
        "source": Path(rel_path).stem,
        "date": None,
        "topic": None,
        "authority": None,
        "age_min_months": MIN_AGE_MONTHS,
        "age_max_months": MAX_AGE_MONTHS,
        "url": None,
    }


def _metadata_from_entry(entry: ManifestEntry) -> dict:
    return {
        "source": entry.source,
        "date": entry.year,
        "topic": entry.topic,
        "authority": entry.authority,
        "age_min_months": entry.age_min_months,
        "age_max_months": entry.age_max_months,
        "url": entry.url,
    }


def load_corpus(corpus_dir: str | Path) -> list[dict]:
    """Load all documents from a directory tree, attaching manifest metadata.

    Supports Markdown (.md), text (.txt) and PDF (.pdf) files.

    Returns:
        List of dicts with ``content``, ``source``, ``path``, ``filename``,
        ``document_id``, ``date``, ``topic``, ``authority``, ``age_min_months``,
        ``age_max_months`` and ``url``. PDF pages also carry ``page``.

    Raises:
        FileNotFoundError: if ``corpus_dir`` does not exist.
        ValueError: if the manifest is present but invalid.
    """
    corpus_dir = Path(corpus_dir)
    if not corpus_dir.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    manifest = load_manifest(corpus_dir)
    seen_files: set[str] = set()
    documents: list[dict] = []

    def describe(abs_path: str, extra: dict | None = None) -> dict:
        rel = Path(abs_path).resolve().relative_to(corpus_dir.resolve()).as_posix()
        seen_files.add(rel)
        entry = manifest.get(rel)
        if entry is None:
            logger.warning("%s is not listed in %s; using default metadata", rel, MANIFEST_FILENAME)
            meta = _default_metadata(rel)
        else:
            meta = _metadata_from_entry(entry)
        return {
            "path": abs_path,
            "filename": Path(abs_path).name,
            "document_id": document_id_for(rel),
            **meta,
            **(extra or {}),
        }

    for pattern in _TEXT_GLOBS:
        loader = DirectoryLoader(
            str(corpus_dir),
            glob=pattern,
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            exclude=[MANIFEST_FILENAME],
        )
        try:
            for doc in loader.load():
                documents.append({"content": doc.page_content, **describe(doc.metadata["source"])})
        except Exception as exc:
            logger.warning("Failed to load %s documents: %s", pattern, exc)

    pdf_loader = DirectoryLoader(str(corpus_dir), glob="**/*.pdf", loader_cls=PyPDFLoader)
    try:
        for doc in pdf_loader.load():
            documents.append(
                {
                    "content": doc.page_content,
                    **describe(doc.metadata["source"], {"page": doc.metadata.get("page")}),
                }
            )
    except Exception as exc:
        logger.warning("Failed to load PDF documents: %s", exc)

    for rel, entry in manifest.items():
        if rel not in seen_files:
            logger.error(
                "%s lists %s (%s) but the file is missing; skipping it",
                MANIFEST_FILENAME,
                rel,
                entry.source,
            )

    if not documents:
        logger.warning("No documents found in %s", corpus_dir)
    else:
        logger.info("Loaded %d documents from %s", len(documents), corpus_dir)

    # Deterministic order regardless of filesystem enumeration.
    documents.sort(key=lambda d: (d["document_id"], d.get("page") or 0))
    return documents
