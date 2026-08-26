"""Live retrieval validation against the real corpus and OpenRouter embeddings (task 4.4).

Skipped unless OPENROUTER_API_KEY is configured and milvus.db exists. Logs the top-1
cosine score for every question so the relevance floor can be tuned (design Decision 7).
"""

import logging
from pathlib import Path

import pytest
import yaml

from backend.core.config import get_rag_settings
from backend.db.milvus_knowledge_store import MilvusKnowledgeStore
from backend.knowledge.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)
VALIDATION = Path(__file__).parent / "fixtures" / "retrieval_validation.yaml"

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


def _live_available() -> bool:
    settings = get_rag_settings()
    return bool(settings.openrouter_api_key) and Path(settings.milvus_db_path).exists()


@pytest.fixture(scope="module")
def store():
    if not _live_available():
        pytest.skip("requires OPENROUTER_API_KEY and a populated milvus.db")
    settings = get_rag_settings()
    s = MilvusKnowledgeStore(settings.milvus_db_path, EmbeddingProvider.from_settings(settings))
    yield s
    s.close()


CASES = yaml.safe_load(VALIDATION.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["question"][:50] for c in CASES])
async def test_expected_document_in_top_3(store, case) -> None:
    results = await store.search(case["question"], top_k=3)
    assert results, "no results"
    top_ids = [r.document_id for r in results]
    logger.info(
        "top1=%.3f top3=%.3f %s -> %s",
        results[0].score,
        results[-1].score,
        case["question"],
        top_ids,
    )
    assert set(top_ids) & set(case["expected"]), f"{top_ids} lacks any of {case['expected']}"


async def test_score_ranges_for_floor_tuning(store) -> None:
    """Not an assertion on quality -- records the numbers Decision 7 is tuned against."""
    top1 = []
    for case in CASES:
        results = await store.search(case["question"], top_k=1)
        top1.append(results[0].score)
    ood = [
        "What is the capital of France?",
        "Best adult keto diet plan",
        "Cheapest car insurance",
        "How do Python list comprehensions work?",
        "Marathon training schedule for beginners",
    ]
    ood_scores = [(await store.search(q, top_k=1))[0].score for q in ood]
    logger.info("in-domain top-1: min=%.3f max=%.3f", min(top1), max(top1))
    logger.info("out-of-domain top-1: min=%.3f max=%.3f", min(ood_scores), max(ood_scores))
    assert min(top1) > max(ood_scores), (
        "in-domain and out-of-domain scores overlap; floor cannot separate them"
    )
