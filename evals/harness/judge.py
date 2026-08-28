"""RAGAs generation metrics through the same OpenRouter gateway the application uses
(rag-evaluation spec, *Generation is scored with RAGAs metrics*; design.md Decision 4)."""

import asyncio
from dataclasses import dataclass

from harness.cases import Case

METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


@dataclass
class Sample:
    case_id: str
    strategy: str
    user_input: str
    response: str
    retrieved_contexts: list[str]
    reference: str


def build_sample(case: Case, strategy: str, response: dict) -> Sample | None:
    """A sample for an answered, judged case; None when the case is not judged or gave the
    no-answer message (no contexts, nothing to be faithful to)."""
    from harness.scoring import is_no_answer

    citations = response.get("citations", [])
    if not case.judged or is_no_answer(response.get("answer", ""), citations) or not citations:
        return None
    return Sample(
        case_id=case.id,
        strategy=strategy,
        user_input=case.question,
        response=response["answer"],
        # The passages the service actually placed in context, in citation order.
        retrieved_contexts=[c["excerpt"] for c in citations if c.get("excerpt")],
        reference=case.expect.reference or "",
    )


class Judge:
    def __init__(self, model: str, embedding_model: str, api_key: str, base_url: str) -> None:
        from openai import AsyncOpenAI
        from ragas.embeddings import OpenAIEmbeddings
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecisionWithoutReference,
            ContextRecall,
            Faithfulness,
        )

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        # The default 1024 output tokens truncates statement extraction on long answers
        # (meal plans, the fish lists); RAGAs itself suggests 4096+.
        llm = llm_factory(model, provider="openai", client=client, max_tokens=4096)
        embeddings = OpenAIEmbeddings(client=client, model=embedding_model)
        self.model = model
        self.faithfulness = Faithfulness(llm=llm)
        self.answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)
        self.context_precision = ContextPrecisionWithoutReference(llm=llm)
        self.context_recall = ContextRecall(llm=llm)

    async def score(self, sample: Sample) -> dict[str, float | None]:
        async def value(coro) -> float | None:
            try:
                return float((await coro).value)
            except Exception as exc:  # a judge failure is a missing score, not a crash
                return None if _log_failure(sample, exc) else None

        return dict(
            zip(
                METRICS,
                await asyncio.gather(
                    value(
                        self.faithfulness.ascore(
                            user_input=sample.user_input,
                            response=sample.response,
                            retrieved_contexts=sample.retrieved_contexts,
                        )
                    ),
                    value(
                        self.answer_relevancy.ascore(
                            user_input=sample.user_input, response=sample.response
                        )
                    ),
                    value(
                        self.context_precision.ascore(
                            user_input=sample.user_input,
                            response=sample.response,
                            retrieved_contexts=sample.retrieved_contexts,
                        )
                    ),
                    value(
                        self.context_recall.ascore(
                            user_input=sample.user_input,
                            retrieved_contexts=sample.retrieved_contexts,
                            reference=sample.reference,
                        )
                    ),
                ),
                strict=True,
            )
        )

    async def score_all(
        self, samples: list[Sample], concurrency: int = 4
    ) -> dict[tuple[str, str], dict]:
        gate = asyncio.Semaphore(concurrency)

        async def one(sample: Sample):
            async with gate:
                return (sample.case_id, sample.strategy), await self.score(sample)

        return dict(await asyncio.gather(*(one(s) for s in samples)))


def _log_failure(sample: Sample, exc: Exception) -> bool:
    print(f"  judge failed for {sample.case_id}/{sample.strategy}: {type(exc).__name__}: {exc}")
    return False
