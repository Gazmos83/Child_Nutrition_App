"""Prompts, fixed messages, and context construction (Day 3 design.md Decisions 8 & 14).

Everything that shapes the *generation* step lives here and is shared by both retrieval
strategies, so Day 6's A/B comparison measures retrieval alone. The no-answer message and
the disclaimer are code constants attached by the pipeline; the model never writes or
rephrases them.
"""

from backend.db.knowledge_store import Document
from backend.schemas.rag import Citation

DISCLAIMER = (
    "This is general information from published pediatric nutrition guidelines, not "
    "medical advice. Please consult your pediatrician about your child's individual needs."
)

NO_ANSWER_MESSAGE = (
    "I wasn't able to find this in my sources. I answer from pediatric nutrition "
    "guidelines that cover children from birth to about four years, and this question "
    "falls outside what they cover. If it's about your child's health, your pediatrician "
    "is the best person to ask."
)

SYSTEM_PROMPT = """You are a child-nutrition assistant for parents of children from birth to
about four years old. You answer from published pediatric guidelines (WHO, AAP, CDC,
USDA/HHS, NIH, FDA/EPA).

How to answer:
- Use ONLY the numbered context blocks provided. Do not use outside knowledge. If the
  blocks do not contain the answer, say so plainly in one or two sentences instead of
  guessing.
- Lead with the answer in the first sentence, then give the supporting detail. Be concise
  and direct.
- Write in plain language for a parent, not a clinician. The first time you use a
  technical term (for example "complementary feeding" or "z-score"), explain it in a few
  words.
- Use short paragraphs. Use a bulleted list for lists of foods or steps.
- State safety points firmly and calmly, without alarm or judgment.
- Do not restate the question and do not add filler.
- Cite the blocks you rely on inline with their numbers in square brackets, like [1] or
  [2][3]. Every factual claim should carry a citation.
- Report quantities only as the sources state them (for example "11 mg of iron a day for
  7–12 months"). Never calculate a specific amount for an individual child from their
  weight or age; if the parent asks for that, say a pediatrician can work it out for their
  child.
- Do not add your own disclaimer; one is attached automatically."""

USER_PROMPT_TEMPLATE = """Context blocks:

{context}

Question: {question}"""

TRANSLATE_SYSTEM_PROMPT = """You rewrite a parent's child-nutrition question into alternative
search queries for a guideline knowledge base. Produce up to {n} rephrasings that keep the
same meaning but use different wording — for example clinical terms instead of everyday
ones ("complementary feeding" for "starting solids"), or the general topic behind a
specific ask. Keep any age exactly as given. Return ONLY a JSON array of strings, nothing
else."""


def format_block(index: int, doc: Document) -> str:
    """Render one numbered context block: ``[n] Source (Year) — topic, section`` + text."""
    header = doc.source
    if doc.date:
        header += f" ({doc.date})"
    descriptors = [d for d in (doc.topic, doc.section) if d]
    if descriptors:
        header += " — " + ", ".join(descriptors)
    return f"[{index}] {header}\n{doc.content.strip()}"


def build_context(chunks: list[Document], budget: int) -> tuple[str, list[Citation]]:
    """Assemble numbered context blocks within ``budget`` characters.

    Blocks are added in the given (rank) order until the next one would exceed the
    budget. The first block is always included (truncated if it alone exceeds the
    budget) so a non-empty retrieval never yields empty context. The returned citations
    are exactly the included blocks, in the same order and numbering (Decision 8).
    """
    blocks: list[str] = []
    citations: list[Citation] = []
    used = 0
    for doc in chunks:
        index = len(blocks) + 1
        block = format_block(index, doc)
        if blocks and used + len(block) + 2 > budget:
            break
        if not blocks and len(block) > budget:
            block = block[:budget]
        blocks.append(block)
        used += len(block) + 2
        citations.append(
            Citation(
                index=index,
                source=doc.source or "unknown",
                year=doc.date,
                topic=doc.topic,
                section=doc.section,
                document_id=doc.document_id,
                score=doc.score,
                excerpt=doc.content.strip(),
            )
        )
    return "\n\n".join(blocks), citations


def build_user_prompt(question: str, context: str) -> str:
    return USER_PROMPT_TEMPLATE.format(context=context, question=question)
