"""MilvusKnowledgeStore against a temporary Milvus Lite database (Day 3 tasks 2.3-2.5)."""

import inspect
from pathlib import Path

import pytest

from backend.db.knowledge_store import Document, SearchFilter
from backend.db.milvus_knowledge_store import (
    COLLECTION_NAME,
    MilvusKnowledgeStore,
    chunk_id,
    render_filter,
)
from tests.fixtures.stub_embedder import StubEmbedder


async def make_docs(
    embedder: StubEmbedder, spec: list[tuple[str, str, int, int]]
) -> list[Document]:
    """spec: (document_id, content, age_min, age_max) -> one embedded chunk each."""
    docs = [
        Document(
            content=content,
            source=f"Source {doc_id}",
            date=2020,
            topic="test",
            authority="WHO",
            section="Intro",
            document_id=doc_id,
            age_min_months=lo,
            age_max_months=hi,
            chunk_index=0,
            content_hash=f"hash-{doc_id}",
        )
        for doc_id, content, lo, hi in spec
    ]
    vectors = await embedder.embed_texts([d.content for d in docs])
    for d, v in zip(docs, vectors, strict=True):
        d.embedding = v
    return docs


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def embedder() -> StubEmbedder:
    return StubEmbedder()


@pytest.fixture
async def store(db_path: str, embedder: StubEmbedder):
    s = MilvusKnowledgeStore(db_path, embedder)
    yield s
    s.close()


CORPUS = [
    ("iron", "Infants 7 to 12 months need 11 mg of iron each day from iron-rich foods.", 7, 12),
    ("honey", "Do not give honey to infants under 12 months because of botulism risk.", 0, 12),
    ("milk", "Toddlers 12 to 24 months can drink whole cow's milk, 16 to 24 ounces daily.", 12, 24),
    ("preschool", "Preschoolers aged 3 to 5 years benefit from regular family meals.", 36, 60),
]


class TestCollectionLifecycle:
    def test_construction_is_lazy(self, db_path: str, embedder: StubEmbedder) -> None:
        MilvusKnowledgeStore(db_path, embedder)
        assert not Path(db_path).exists()

    async def test_search_before_ingest_points_at_ingest_script(self, store) -> None:
        with pytest.raises(RuntimeError, match="scripts/ingest.py"):
            await store.search("iron")
        assert await store.count() == 0
        assert await store.list_document_hashes() == {}

    async def test_collection_is_created_once_and_records_model(
        self, store, embedder: StubEmbedder
    ) -> None:
        await store.upsert(await make_docs(embedder, CORPUS[:1]))
        await store.upsert(await make_docs(embedder, CORPUS[1:2]))
        client = store._connect()
        assert client.list_collections() == [COLLECTION_NAME]
        props = client.describe_collection(COLLECTION_NAME)["properties"]
        assert props["kb.embedding_model"] == "stub/bag-of-words"
        assert props["kb.dimension"] == "32"

    async def test_reopening_with_another_model_is_refused(
        self, db_path: str, embedder: StubEmbedder
    ) -> None:
        first = MilvusKnowledgeStore(db_path, embedder)
        await first.upsert(await make_docs(embedder, CORPUS[:1]))
        first.close()

        other = MilvusKnowledgeStore(db_path, StubEmbedder(model_name="other/model"))
        with pytest.raises(RuntimeError) as exc_info:
            await other.search("iron")
        message = str(exc_info.value)
        assert "stub/bag-of-words" in message
        assert "other/model" in message
        assert "scripts/ingest.py" in message
        other.close()


class TestSearch:
    async def test_returns_documents_with_scores_ranked(self, store, embedder) -> None:
        await store.upsert(await make_docs(embedder, CORPUS))
        results = await store.search("how much iron does an infant need each day", top_k=3)
        assert len(results) == 3
        assert results[0].document_id == "iron"
        assert all(isinstance(r.score, float) for r in results)
        assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
        top = results[0]
        assert (top.source, top.date, top.authority, top.section) == (
            "Source iron",
            2020,
            "WHO",
            "Intro",
        )
        assert (top.age_min_months, top.age_max_months) == (7, 12)
        assert top.embedding is None

    async def test_age_filter_keeps_only_overlapping_ranges(self, store, embedder) -> None:
        await store.upsert(await make_docs(embedder, CORPUS))
        results = await store.search(
            "food", top_k=10, filter=SearchFilter(age_min_months=8, age_max_months=8)
        )
        ids = {r.document_id for r in results}
        assert ids == {"iron", "honey"}
        for r in results:
            assert r.age_min_months <= 8 <= r.age_max_months

    async def test_authority_filter(self, store, embedder) -> None:
        docs = await make_docs(embedder, CORPUS)
        docs[0].authority = "AAP"
        await store.upsert(docs)
        results = await store.search("iron", top_k=10, filter=SearchFilter(authorities=("AAP",)))
        assert [r.document_id for r in results] == ["iron"]

    async def test_blank_query_returns_nothing_without_touching_store(self, store) -> None:
        assert await store.search("   ") == []

    async def test_count_matches_rows(self, store, embedder) -> None:
        await store.upsert(await make_docs(embedder, CORPUS))
        assert await store.count() == len(CORPUS)


class TestFilterRendering:
    """Decision 5: expressions come from validated fields only."""

    def test_age_overlap_expression(self) -> None:
        expr = render_filter(SearchFilter(age_min_months=6, age_max_months=8))
        assert expr == "age_min_months <= 8 and age_max_months >= 6"

    def test_authority_expression_is_json_quoted(self) -> None:
        expr = render_filter(SearchFilter(authorities=("WHO", "USDA/HHS")))
        assert expr == 'authority in ["WHO", "USDA/HHS"]'

    def test_combined_and_empty(self) -> None:
        both = render_filter(SearchFilter(age_min_months=8, authorities=("AAP",)))
        assert both == 'age_min_months <= 8 and age_max_months >= 8 and authority in ["AAP"]'
        assert render_filter(None) == "" and render_filter(SearchFilter()) == ""

    def test_no_public_method_accepts_a_raw_expression(self) -> None:
        for name, member in inspect.getmembers(MilvusKnowledgeStore, inspect.isfunction):
            if name.startswith("_"):
                continue
            params = inspect.signature(member).parameters
            assert "expr" not in params and "expression" not in params, name
            if "filter" in params:
                assert "SearchFilter" in str(params["filter"].annotation)


class TestUpsertIdempotency:
    def test_chunk_ids_are_deterministic(self) -> None:
        assert chunk_id("who-iron", 3) == chunk_id("who-iron", 3)
        assert chunk_id("who-iron", 3) != chunk_id("who-iron", 4)
        assert chunk_id("who-iron", 3) != chunk_id("aap-iron", 3)
        assert len(chunk_id("x", 0)) == 32

    async def test_reingesting_same_document_changes_nothing(self, store, embedder) -> None:
        docs = await make_docs(embedder, CORPUS[:2])
        await store.upsert(docs)
        client = store._connect()
        before = {
            r["id"]
            for r in client.query(COLLECTION_NAME, filter="chunk_index >= 0", output_fields=["id"])
        }
        await store.upsert(await make_docs(embedder, CORPUS[:2]))
        after = {
            r["id"]
            for r in client.query(COLLECTION_NAME, filter="chunk_index >= 0", output_fields=["id"])
        }
        assert before == after
        assert await store.count() == 2

    async def test_shrunken_document_leaves_no_stale_chunks(self, store, embedder) -> None:
        three = []
        for i, text in enumerate(["part one iron", "part two iron", "part three iron"]):
            d = Document(content=text, source="S", document_id="doc", chunk_index=i)
            three.append(d)
        for d, v in zip(three, await embedder.embed_texts([d.content for d in three]), strict=True):
            d.embedding = v
        await store.upsert(three)
        assert await store.count() == 3

        one = Document(content="only part", source="S", document_id="doc", chunk_index=0)
        one.embedding = (await embedder.embed_texts([one.content]))[0]
        await store.upsert([one])
        assert await store.count() == 1
        results = await store.search("part", top_k=10)
        assert [r.content for r in results] == ["only part"]

    async def test_list_document_hashes(self, store, embedder) -> None:
        await store.upsert(await make_docs(embedder, CORPUS))
        hashes = await store.list_document_hashes()
        assert hashes == {doc_id: f"hash-{doc_id}" for doc_id, *_ in CORPUS}

    async def test_delete_removes_document(self, store, embedder) -> None:
        await store.upsert(await make_docs(embedder, CORPUS))
        assert await store.delete("honey") == 1
        assert await store.delete("honey") == 0
        assert await store.count() == len(CORPUS) - 1

    async def test_upsert_requires_embedding_and_id(self, store) -> None:
        with pytest.raises(ValueError, match="no embedding"):
            await store.upsert([Document(content="x", source="s", document_id="d")])
        with pytest.raises(ValueError, match="no document_id"):
            await store.upsert([Document(content="x", source="s", embedding=[0.0] * 32)])
