"""Tone constants and context construction (Day 3 task 5.1; design Decisions 8 and 14)."""

from backend.db.knowledge_store import Document
from backend.rag.prompts import (
    DISCLAIMER,
    NO_ANSWER_MESSAGE,
    SYSTEM_PROMPT,
    TRANSLATE_SYSTEM_PROMPT,
    build_context,
    build_user_prompt,
    format_block,
)


def doc(i: int, n_chars: int = 200, **overrides) -> Document:
    base = dict(
        content=f"Passage {i}. " + ("x" * max(0, n_chars - 12)),
        source=f"Source {i}",
        date=2000 + i,
        topic="topic",
        section=f"Section {i}",
        document_id=f"doc-{i}",
        score=0.9 - i / 100,
    )
    base.update(overrides)
    return Document(**base)


class TestToneConstants:
    def test_system_prompt_encodes_the_tone_rules(self) -> None:
        p = SYSTEM_PROMPT.lower()
        assert "lead with the answer" in p
        assert "plain language" in p
        assert "explain it" in p and "technical term" in p
        assert "only the numbered context blocks" in p
        assert "[1]" in SYSTEM_PROMPT
        assert "never calculate a specific amount for an individual child" in p
        assert "without alarm or judgment" in p
        assert "do not restate the question" in p
        assert "do not add your own disclaimer" in p

    def test_no_answer_message_is_warm_and_explains_why(self) -> None:
        m = NO_ANSWER_MESSAGE
        assert "birth to about four years" in m
        assert "pediatrician" in m
        assert "falls outside" in m
        assert len(m.split()) < 80  # concise

    def test_disclaimer_is_fixed_text(self) -> None:
        assert "not" in DISCLAIMER and "medical advice" in DISCLAIMER
        assert "pediatrician" in DISCLAIMER

    def test_translate_prompt_preserves_age_and_asks_for_json(self) -> None:
        assert "{n}" in TRANSLATE_SYSTEM_PROMPT
        assert "age exactly as given" in TRANSLATE_SYSTEM_PROMPT
        assert "JSON array" in TRANSLATE_SYSTEM_PROMPT


class TestContextConstruction:
    def test_block_format(self) -> None:
        block = format_block(2, doc(2, content="Body text."))
        assert block.startswith("[2] Source 2 (2002) — topic, Section 2\n")
        assert block.endswith("Body text.")

    def test_block_omits_missing_metadata(self) -> None:
        block = format_block(1, Document(content="t", source="S"))
        assert block == "[1] S\nt"

    def test_budget_is_respected_and_citations_match(self) -> None:
        chunks = [doc(i, n_chars=300) for i in range(1, 8)]
        context, citations = build_context(chunks, budget=1000)
        assert 0 < len(citations) < len(chunks)
        assert len(context) <= 1000
        assert [c.index for c in citations] == list(range(1, len(citations) + 1))
        assert [c.document_id for c in citations] == [
            f"doc-{i}" for i in range(1, len(citations) + 1)
        ]
        for c in citations:
            assert f"[{c.index}] {c.source}" in context
            assert c.excerpt in context

    def test_first_block_always_included(self) -> None:
        context, citations = build_context([doc(1, n_chars=5000)], budget=500)
        assert len(citations) == 1 and len(context) == 500

    def test_empty_input(self) -> None:
        assert build_context([], budget=100) == ("", [])

    def test_citations_carry_score_and_year(self) -> None:
        _, citations = build_context([doc(3)], budget=10_000)
        assert citations[0].year == 2003 and citations[0].score == 0.87

    def test_user_prompt_contains_context_and_question(self) -> None:
        prompt = build_user_prompt("How much iron?", "[1] S\nt")
        assert prompt.index("[1] S") < prompt.index("Question: How much iron?")
