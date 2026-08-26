"""Incremental ingestion against a temp Milvus Lite database (Day 3 task 4.1)."""

from pathlib import Path

import pytest

from backend.db.milvus_knowledge_store import MilvusKnowledgeStore
from backend.knowledge.chunker import chunk_documents
from backend.knowledge.ingestion import run_ingestion
from tests.fixtures.stub_embedder import StubEmbedder

MANIFEST = """
documents:
  - file: iron.md
    source: Iron Guidance
    year: 2010
    topic: iron
    authority: AAP
    age_min_months: 0
    age_max_months: 36
  - file: honey.md
    source: Honey Guidance
    year: 2024
    topic: honey
    authority: CDC
    age_min_months: 0
    age_max_months: 12
"""

IRON = "# Iron\n\n## Needs\n\n" + "Infants 7 to 12 months need 11 mg of iron a day. " * 30
HONEY = "# Honey\n\n## Rule\n\n" + "Do not give honey to infants under 12 months. " * 5


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "manifest.yaml").write_text(MANIFEST)
    (kb / "iron.md").write_text(IRON)
    (kb / "honey.md").write_text(HONEY)
    return kb


@pytest.fixture
async def store(tmp_path: Path):
    embedder = StubEmbedder()
    s = MilvusKnowledgeStore(str(tmp_path / "kb.db"), embedder)
    yield s, embedder
    s.close()


class TestChunkerSections:
    def test_chunks_carry_nearest_heading_and_metadata(self) -> None:
        doc = {
            "content": "# Title\n\nIntro text.\n\n## First\n\n"
            + "a " * 300
            + "\n\n## Second\n\nb b b.",
            "source": "S",
            "document_id": "d",
            "age_min_months": 6,
            "age_max_months": 23,
            "content_hash": "h",
        }
        chunks = chunk_documents([doc])
        assert chunks[0]["section"] is None  # before any ## heading
        assert any(c["section"] == "First" for c in chunks)
        assert chunks[-1]["section"] == "Second"
        for c in chunks:
            assert (c["age_min_months"], c["age_max_months"], c["content_hash"]) == (6, 23, "h")
        assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


class TestIncrementalIngestion:
    async def test_first_run_embeds_everything(self, corpus: Path, store) -> None:
        s, embedder = store
        summary = await run_ingestion(corpus, s, embedder)
        assert (summary.loaded, summary.new, summary.changed, summary.unchanged) == (2, 2, 0, 0)
        assert summary.chunks_embedded > 2
        assert summary.chunks_upserted == summary.chunks_embedded
        assert await s.count() == summary.chunks_upserted

    async def test_second_run_embeds_nothing(self, corpus: Path, store) -> None:
        s, embedder = store
        first = await run_ingestion(corpus, s, embedder)
        calls_after_first = embedder.calls
        second = await run_ingestion(corpus, s, embedder)
        assert (second.unchanged, second.new, second.changed) == (2, 0, 0)
        assert second.chunks_embedded == 0
        assert embedder.calls == calls_after_first
        assert await s.count() == first.chunks_upserted

    async def test_editing_one_file_reembeds_only_that_document(self, corpus: Path, store) -> None:
        s, embedder = store
        first = await run_ingestion(corpus, s, embedder)
        honey_chunks = len(
            chunk_documents([{"content": HONEY, "document_id": "honey", "source": "x"}])
        )
        iron_chunks = first.chunks_upserted - honey_chunks

        (corpus / "honey.md").write_text(
            HONEY + "\n\n## Update\n\nPasteurised honey is not safe either."
        )
        third = await run_ingestion(corpus, s, embedder)
        assert (third.unchanged, third.new, third.changed) == (1, 0, 1)
        assert 0 < third.chunks_embedded <= honey_chunks + 2
        hashes = await s.list_document_hashes()
        assert set(hashes) == {"iron", "honey"}
        # Iron untouched; honey fully replaced (no stale chunks, new count).
        results = await s.search("iron", top_k=50)
        assert sum(r.document_id == "iron" for r in results) == iron_chunks
        assert await s.count() == iron_chunks + third.chunks_upserted

    async def test_document_removed_from_corpus_is_reported_not_deleted(
        self, corpus: Path, store
    ) -> None:
        s, embedder = store
        await run_ingestion(corpus, s, embedder)
        (corpus / "honey.md").unlink()
        summary = await run_ingestion(corpus, s, embedder)
        assert summary.stale_document_ids == ["honey"]
        assert "honey" in await s.list_document_hashes()

    async def test_metadata_reaches_the_store(self, corpus: Path, store) -> None:
        s, embedder = store
        await run_ingestion(corpus, s, embedder)
        top = (await s.search("honey botulism", top_k=1))[0]
        assert top.document_id == "honey"
        assert (top.source, top.date, top.authority, top.topic) == (
            "Honey Guidance",
            2024,
            "CDC",
            "honey",
        )
        assert (top.age_min_months, top.age_max_months) == (0, 12)
        assert top.section == "Rule"
        assert top.content_hash

    async def test_empty_corpus(self, tmp_path: Path, store) -> None:
        s, embedder = store
        empty = tmp_path / "empty"
        empty.mkdir()
        summary = await run_ingestion(empty, s, embedder)
        assert summary.loaded == 0 and embedder.calls == 0
