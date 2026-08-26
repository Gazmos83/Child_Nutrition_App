"""Basic and advanced retrievers with in-memory store and fake model (tasks 5.3, 5.4)."""

from backend.db.knowledge_store import Document
from backend.rag.retrievers import (
    AdvancedRetriever,
    BasicRetriever,
    _parse_alternatives,
    deduplicate,
    reciprocal_rank_fusion,
)
from tests.fixtures.fake_llm import RecordingChatModel
from tests.fixtures.memory_store import InMemoryKnowledgeStore


def d(
    doc_id: str, content: str, lo: int = 0, hi: int = 60, idx: int = 0, score: float | None = None
) -> Document:
    return Document(
        content=content,
        source=f"Source {doc_id}",
        date=2020,
        authority="AAP",
        document_id=doc_id,
        chunk_index=idx,
        age_min_months=lo,
        age_max_months=hi,
        score=score,
    )


CORPUS = [
    d("iron", "Infants 7 to 12 months need 11 mg of iron each day from iron rich foods", 7, 12),
    d("honey", "Do not give honey to infants under 12 months because of botulism", 0, 12),
    d("milk", "Toddlers can drink whole cow milk after 12 months, 16 to 24 ounces a day", 12, 24),
    d(
        "preschool",
        "Preschoolers aged 3 to 5 years need family meals and 1000 to 1400 calories",
        36,
        60,
    ),
    d("general", "Offer a variety of foods every day and feed responsively at every age", 0, 60),
]


class TestBasicRetriever:
    async def test_single_query_ranked(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        result = await BasicRetriever(store, top_k=3).retrieve("how much iron do infants need")
        assert result.queries == ["how much iron do infants need"]
        assert result.filters == {} and not result.filter_dropped
        assert result.chunks[0].document_id == "iron"
        assert len(result.chunks) <= 3
        assert store.calls == [("how much iron do infants need", None)]


class TestFusion:
    def test_chunk_in_two_lists_beats_chunk_in_one(self) -> None:
        a, b, x, y = d("a", "a"), d("b", "b"), d("x", "x"), d("y", "y")
        fused = reciprocal_rank_fusion([[x, y, a], [x, y, a], [y, x, b]])
        ids = [c.document_id for c in fused]
        assert ids.index("a") < ids.index("b")  # both rank 3rd; A appears twice

    def test_keeps_max_score_across_lists(self) -> None:
        low = d("a", "a", score=0.2)
        high = d("a", "a", score=0.9)
        fused = reciprocal_rank_fusion([[low], [high]])
        assert len(fused) == 1 and fused[0].score == 0.9

    def test_deterministic_tie_break(self) -> None:
        one = reciprocal_rank_fusion([[d("b", "b", score=0.5), d("a", "a", score=0.5)]])
        two = reciprocal_rank_fusion([[d("b", "b", score=0.5), d("a", "a", score=0.5)]])
        assert [c.document_id for c in one] == [c.document_id for c in two]


class TestDedup:
    def test_same_chunk_once(self) -> None:
        c = d("iron", "same text", idx=2)
        assert len(deduplicate([c, d("iron", "same text", idx=2)])) == 1

    def test_overlapping_chunk_from_same_document_removed(self) -> None:
        first = d("doc", "infants need iron rich foods every day from six months onward", idx=0)
        overlap = d("doc", "infants need iron rich foods every day from six months", idx=1)
        other = d("other", "infants need iron rich foods every day from six months", idx=0)
        kept = deduplicate([first, overlap, other])
        assert [(c.document_id, c.chunk_index) for c in kept] == [("doc", 0), ("other", 0)]

    def test_distinct_chunks_kept(self) -> None:
        a = d("doc", "iron needs at seven months", idx=0)
        b = d("doc", "vitamin d drops for breastfed babies", idx=1)
        assert len(deduplicate([a, b])) == 2


class TestParseAlternatives:
    def test_json_array_with_fence_and_dupes(self) -> None:
        text = (
            '```json\n["Iron needs for infants", "iron needs for infants", "", 5, '
            '"Infant iron intake"]\n```'
        )
        assert _parse_alternatives(text, "Iron needs for infants", 3) == ["Infant iron intake"]

    def test_garbage_returns_empty(self) -> None:
        assert _parse_alternatives("Sure! Here are some ideas.", "q", 3) == []
        assert _parse_alternatives("[not json", "q", 3) == []

    def test_limit(self) -> None:
        assert len(_parse_alternatives('["a","b","c","d"]', "q", 2)) == 2


class TestAdvancedRetriever:
    async def test_alternatives_recorded_and_issued(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        llm = RecordingChatModel(
            responses=['["infant iron requirements", "iron intake for babies"]']
        )
        result = await AdvancedRetriever(store, llm).retrieve("how much iron does a baby need")
        assert result.queries == [
            "how much iron does a baby need",
            "infant iron requirements",
            "iron intake for babies",
        ]
        assert [q for q, _ in store.calls] == result.queries
        assert result.chunks[0].document_id == "iron"
        # "baby" -> 0-12 months filter applied and recorded
        assert result.filters == {"age_min_months": 0, "age_max_months": 12}
        assert all(f is not None and f.age_min_months == 0 for _, f in store.calls)

    async def test_translation_failure_degrades_to_original(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        llm = RecordingChatModel(responses=[], fail_with="boom")
        result = await AdvancedRetriever(store, llm).retrieve("what is fiber")
        assert result.queries == ["what is fiber"]
        assert result.filters == {} and not result.filter_dropped

    async def test_no_model_means_no_translation(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        result = await AdvancedRetriever(store, None).retrieve("honey for infants")
        assert result.queries == ["honey for infants"]
        assert result.chunks[0].document_id == "honey"

    async def test_age_filter_excludes_non_overlapping(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        result = await AdvancedRetriever(store, None).retrieve(
            "what can my 8-month-old eat every day"
        )
        ids = {c.document_id for c in result.chunks}
        assert "preschool" not in ids and "milk" not in ids
        assert "general" in ids  # 0-60 overlaps
        assert result.filters == {"age_min_months": 8, "age_max_months": 8}

    async def test_filter_dropped_when_it_empties_results(self) -> None:
        store = InMemoryKnowledgeStore([d("preschool", "family meals for preschoolers", 36, 60)])
        result = await AdvancedRetriever(store, None).retrieve("family meals for my 8-month-old")
        assert result.filter_dropped is True
        assert result.filters == {}
        assert [c.document_id for c in result.chunks] == ["preschool"]
        assert [f for _, f in store.calls] == [store.calls[0][1], None]

    async def test_duplicates_across_queries_collapse(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        llm = RecordingChatModel(responses=['["honey botulism infants"]'])
        result = await AdvancedRetriever(store, llm).retrieve("honey botulism infants")
        keys = [(c.document_id, c.chunk_index) for c in result.chunks]
        assert len(keys) == len(set(keys))

    async def test_top_k_final(self) -> None:
        store = InMemoryKnowledgeStore(CORPUS)
        result = await AdvancedRetriever(store, None, top_k_final=2).retrieve("foods every day")
        assert len(result.chunks) <= 2
