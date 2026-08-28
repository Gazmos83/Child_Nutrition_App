"""The evaluation test set stays valid (rag-evaluation spec, *The test set covers every
category the product meets*). Plain YAML only -- the evals project has its own environment
and this guard must run in the main suite without it."""

from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "cases.yaml"
MANIFEST = ROOT / "knowledge-base" / "manifest.yaml"
SEED = ROOT / "tests" / "fixtures" / "retrieval_validation.yaml"

CATEGORIES = {
    "rag_basic",
    "rag_advanced",
    "tool",
    "hybrid",
    "user_data",
    "out_of_domain",
    "adversarial",
}
TOOL_NAMES = {
    "calculate_bmi",
    "calculate_calorie_target",
    "calculate_protein_target",
    "lookup_food",
    "calculate_meal_nutrition",
    "generate_meal_plan",
    "log_feeding",
    "get_daily_nutrition",
    "get_remaining_targets",
    "detect_nutrient_gaps",
}
OOD_PROBES = [
    "What is the capital of France?",
    "Best adult keto diet plan",
    "Cheapest car insurance",
    "How do Python list comprehensions work?",
    "Marathon training schedule for beginners",
]


def load():
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    return data["fixtures"], data["cases"]


def manifest_ids() -> set[str]:
    docs = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    docs = docs if isinstance(docs, list) else docs.get("documents", docs)
    return {Path(d["file"]).stem for d in docs}


def test_size_and_unique_ids() -> None:
    _, cases = load()
    assert 40 <= len(cases) <= 60
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_every_category_present_at_least_three_times() -> None:
    _, cases = load()
    counts = Counter(c["category"] for c in cases)
    assert set(counts) == CATEGORIES
    assert all(n >= 3 for n in counts.values()), counts


def test_expected_documents_exist_in_the_manifest() -> None:
    _, cases = load()
    known = manifest_ids()
    for case in cases:
        for doc in case["expect"].get("documents", []):
            assert doc in known, f"{case['id']}: {doc}"
        source = case["expect"].get("reference_source")
        if source is not None:
            assert source in known, f"{case['id']}: {source}"


def test_expected_tools_are_real_tools() -> None:
    _, cases = load()
    for case in cases:
        for tool in case["expect"].get("tools", []):
            assert tool in TOOL_NAMES, f"{case['id']}: {tool}"


def test_fixtures_referenced_exist() -> None:
    fixtures, cases = load()
    for case in cases:
        for key in ("child", "feeding_log"):
            if key in case:
                assert case[key] in fixtures, f"{case['id']}: {key}={case[key]}"


def test_seed_questions_are_retained() -> None:
    _, cases = load()
    questions = {c["question"] for c in cases}
    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["cases"]
    for entry in seed:
        assert entry["question"] in questions, entry["question"]
    for probe in OOD_PROBES:
        assert probe in questions, probe


def test_every_case_has_a_checkable_expectation() -> None:
    _, cases = load()
    for case in cases:
        expect = case["expect"]
        assert any(
            expect.get(k)
            for k in (
                "documents",
                "intent",
                "tools",
                "no_answer",
                "must_include",
                "must_not_include",
            )
        ), case["id"]
        if case["category"] in {"rag_basic", "rag_advanced", "hybrid"}:
            assert expect.get("reference") and expect.get("reference_source"), case["id"]
