"""End-to-end against the real corpus, OpenRouter embeddings and chat model (tasks 9.2-9.4).

Skipped unless OPENROUTER_API_KEY is configured and milvus.db exists. Logs every answer so
tone can be spot-checked against design Decision 14.
"""

import logging
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.core.config import get_rag_settings
from backend.main import create_app
from backend.rag.llm import build_pipeline, reset_pipeline_cache
from backend.rag.prompts import DISCLAIMER, NO_ANSWER_MESSAGE

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

CASES = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "retrieval_validation.yaml").read_text()
)["cases"]
SPOT_CHECK = [c["question"] for c in CASES[:5]]
OUT_OF_DOMAIN = [
    "What is the capital of France?",
    "Best adult keto diet plan",
    "Cheapest car insurance",
    "How do Python list comprehensions work?",
    "Marathon training schedule for beginners",
]


@pytest.fixture(scope="module")
def pipeline():
    settings = get_rag_settings()
    if not settings.openrouter_api_key or not Path(settings.milvus_db_path).exists():
        pytest.skip("requires OPENROUTER_API_KEY and a populated milvus.db")
    return build_pipeline(settings)


@pytest.mark.parametrize("strategy", ["basic", "advanced"])
@pytest.mark.parametrize("question", SPOT_CHECK, ids=[q[:40] for q in SPOT_CHECK])
async def test_validation_questions_are_answered_with_citations(
    pipeline, question, strategy
) -> None:
    response = await pipeline.answer(question, strategy)
    logger.info(
        "\n[%s] Q: %s\nA: %s\nqueries=%s filters=%s cites=%s",
        strategy,
        question,
        response.answer,
        response.retrieval.queries,
        response.retrieval.filters,
        [(c.index, c.source, c.year) for c in response.citations],
    )
    assert response.answer != NO_ANSWER_MESSAGE
    assert response.citations, "grounded answer must carry citations"
    assert all(c.source and c.year for c in response.citations)
    assert response.disclaimer == DISCLAIMER
    assert response.strategy == strategy
    assert "[1]" in response.answer or "[" in response.answer, "answer should cite blocks as [n]"
    if strategy == "advanced":
        assert len(response.retrieval.queries) >= 1


@pytest.mark.parametrize("strategy", ["basic", "advanced"])
@pytest.mark.parametrize("question", OUT_OF_DOMAIN, ids=[q[:30] for q in OUT_OF_DOMAIN])
async def test_out_of_domain_gets_the_no_answer_message(pipeline, question, strategy) -> None:
    response = await pipeline.answer(question, strategy)
    logger.info("[%s] OOD %r top_score=%s", strategy, question, response.retrieval.top_score)
    assert response.answer == NO_ANSWER_MESSAGE
    assert response.citations == []
    assert response.disclaimer == DISCLAIMER


def test_api_ask_end_to_end_json() -> None:
    settings = get_rag_settings()
    if not settings.openrouter_api_key or not Path(settings.milvus_db_path).exists():
        pytest.skip("requires OPENROUTER_API_KEY and a populated milvus.db")
    reset_pipeline_cache()
    try:
        with TestClient(create_app()) as client:
            r = client.post(
                "/api/ask",
                json={"question": "Is honey safe for my 9 month old?", "stream": False},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["citations"] and body["disclaimer"] == DISCLAIMER
        assert body["answer"] != NO_ANSWER_MESSAGE
        assert body["retrieval"]["filters"] == {"age_min_months": 9, "age_max_months": 9}
        logger.info("API answer: %s", body["answer"])
    finally:
        reset_pipeline_cache()
