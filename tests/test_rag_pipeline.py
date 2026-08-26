"""RagPipeline: relevance floor, no-answer path, citations, prompt parity (task 5.5)."""

import pytest

from backend.db.knowledge_store import Document
from backend.rag.pipeline import RagPipeline, RagResponse
from backend.rag.prompts import DISCLAIMER, NO_ANSWER_MESSAGE, SYSTEM_PROMPT
from backend.rag.retrievers import AdvancedRetriever, BasicRetriever, RetrievalResult
from tests.fixtures.fake_llm import RecordingChatModel
from tests.fixtures.memory_store import InMemoryKnowledgeStore


def d(doc_id: str, content: str, idx: int = 0) -> Document:
    return Document(
        content=content,
        source=f"Source {doc_id}",
        date=2020,
        topic="t",
        section="s",
        document_id=doc_id,
        chunk_index=idx,
    )


CORPUS = [
    d("iron", "Infants 7 to 12 months need 11 mg of iron each day from iron rich foods"),
    d("honey", "Do not give honey to infants under 12 months because of botulism"),
]


def make_pipeline(
    llm: RecordingChatModel, min_similarity: float = 0.3, budget: int = 6000, store=None
):
    store = store or InMemoryKnowledgeStore(CORPUS)
    return RagPipeline(
        retrievers={"basic": BasicRetriever(store), "advanced": AdvancedRetriever(store, None)},
        chat_model=llm,
        min_similarity=min_similarity,
        context_char_budget=budget,
    )


class TestNoAnswerPath:
    async def test_out_of_domain_question_returns_fixed_message_without_model_call(self) -> None:
        llm = RecordingChatModel(responses=["should not be used"])
        response = await make_pipeline(llm).answer("What is the capital of France?", "basic")
        assert response.answer == NO_ANSWER_MESSAGE
        assert response.citations == []
        assert response.disclaimer == DISCLAIMER
        assert response.retrieval.kept == 0
        assert llm.calls == []

    async def test_floor_filters_weak_matches(self) -> None:
        llm = RecordingChatModel(responses=["x"])
        # "iron" alone overlaps 1/1 tokens -> score 1.0; a 6-word query with one hit -> 0.17
        weak = await make_pipeline(llm, min_similarity=0.5).answer(
            "tell me a story about a dragon and iron", "basic"
        )
        assert (
            weak.answer == NO_ANSWER_MESSAGE
            and weak.retrieval.retrieved >= 1
            and weak.retrieval.kept == 0
        )
        assert weak.retrieval.top_score is not None and weak.retrieval.top_score < 0.5

    async def test_no_answer_is_streamed_as_one_fragment(self) -> None:
        llm = RecordingChatModel(responses=["x"])
        items = [
            item
            async for item in make_pipeline(llm).stream(
                "What is the capital of France?", "advanced"
            )
        ]
        assert items[0] == NO_ANSWER_MESSAGE
        assert isinstance(items[1], RagResponse) and items[1].citations == []
        assert llm.calls == []


class TestAnswerPath:
    async def test_answer_with_citations_matching_context(self) -> None:
        llm = RecordingChatModel(responses=["Infants 7–12 months need 11 mg of iron a day [1]."])
        response = await make_pipeline(llm).answer(
            "how much iron do infants need each day", "basic"
        )
        assert response.answer.startswith("Infants 7–12 months")
        assert response.disclaimer == DISCLAIMER
        assert response.strategy == "basic"
        assert [c.index for c in response.citations] == list(range(1, len(response.citations) + 1))
        assert response.citations[0].document_id == "iron"
        assert response.citations[0].year == 2020 and response.citations[0].source == "Source iron"
        assert response.retrieval.kept == len(response.citations)
        assert response.retrieval.queries == ["how much iron do infants need each day"]

        system, user = llm.calls[0]
        assert system.content == SYSTEM_PROMPT
        assert "[1] Source iron (2020) — t, s" in user.content
        assert user.content.rstrip().endswith("Question: how much iron do infants need each day")

    async def test_prompt_is_identical_across_strategies_for_same_chunks(self) -> None:
        llm = RecordingChatModel(responses=["a", "b"])
        pipeline = make_pipeline(llm)
        await pipeline.answer("iron for infants each day", "basic")
        await pipeline.answer("iron for infants each day", "advanced")
        basic_prompt, advanced_prompt = llm.calls
        assert [m.content for m in basic_prompt] == [m.content for m in advanced_prompt]

    async def test_stream_yields_tokens_then_response(self) -> None:
        llm = RecordingChatModel(responses=["Iron matters [1]. Offer iron rich foods."])
        items = [
            item async for item in make_pipeline(llm).stream("iron rich foods for infants", "basic")
        ]
        *tokens, final = items
        assert all(isinstance(t, str) for t in tokens) and len(tokens) > 1
        assert isinstance(final, RagResponse)
        assert "".join(tokens) == final.answer == "Iron matters [1]. Offer iron rich foods."
        assert final.citations and final.disclaimer == DISCLAIMER

    async def test_stream_failure_propagates(self) -> None:
        llm = RecordingChatModel(
            responses=["one two three four"], fail_with="upstream", fail_after_tokens=2
        )
        received = []
        with pytest.raises(RuntimeError, match="upstream"):
            async for item in make_pipeline(llm).stream("iron for infants", "basic"):
                received.append(item)
        assert received == ["one ", "two "]

    async def test_budget_limits_citations(self) -> None:
        store = InMemoryKnowledgeStore(
            [d("iron", f"iron fact number {i} " + "x" * 300, idx=i) for i in range(6)]
        )
        llm = RecordingChatModel(responses=["ok"])
        response = await make_pipeline(llm, budget=800, store=store).answer("iron fact", "basic")
        assert 0 < response.retrieval.kept < response.retrieval.retrieved

    async def test_unknown_strategy(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            await make_pipeline(RecordingChatModel(responses=[])).answer("q", "hybrid")  # type: ignore[arg-type]


class TestRetrievalResult:
    def test_retrieved_counts_chunks(self) -> None:
        assert RetrievalResult(chunks=CORPUS, queries=["q"]).retrieved == 2


class TestFloorIsJudgedOnTheOriginalQuestion:
    """Decision 7 amendment: a paraphrase may add context but never unlock an answer."""

    async def test_paraphrase_inflated_score_does_not_unlock_an_answer(self) -> None:
        from backend.rag.retrievers import RetrievalResult

        class InflatedRetriever:
            name = "advanced"

            async def retrieve(self, question: str) -> RetrievalResult:
                strong = d("keto", "keto diet plan for adults with high fat and low carbohydrate")
                strong.score = 0.9  # found by a paraphrase
                return RetrievalResult(
                    chunks=[strong], queries=[question, "paraphrase"], question_top_score=0.36
                )

        llm = RecordingChatModel(responses=["should not be used"])
        pipeline = RagPipeline(retrievers={"advanced": InflatedRetriever()}, chat_model=llm)
        response = await pipeline.answer("Best adult keto diet plan", "advanced")
        assert response.answer == NO_ANSWER_MESSAGE
        assert response.citations == [] and llm.calls == []
        assert response.retrieval.top_score == 0.9  # still reported for evaluation

    async def test_in_domain_question_keeps_paraphrase_found_context(self) -> None:
        from backend.rag.retrievers import RetrievalResult

        class Retriever:
            name = "advanced"

            async def retrieve(self, question: str) -> RetrievalResult:
                a = d("iron", "iron needs at 7 to 12 months are 11 mg", idx=0)
                a.score = 0.7
                b = d("iron", "iron rich first foods include meat and fortified cereal", idx=1)
                b.score = 0.5  # only a paraphrase found this one
                return RetrievalResult(
                    chunks=[a, b], queries=[question, "p"], question_top_score=0.7
                )

        llm = RecordingChatModel(responses=["ok [1][2]"])
        pipeline = RagPipeline(retrievers={"advanced": Retriever()}, chat_model=llm)
        response = await pipeline.answer("iron for my baby", "advanced")
        assert len(response.citations) == 2
