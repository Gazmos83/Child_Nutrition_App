from harness.cases import Case
from harness.judge import build_sample
from harness.scoring import NO_ANSWER_PREFIX, score

NO_ANSWER = NO_ANSWER_PREFIX + ". Ask your pediatrician."
IRON = "aap-iron-deficiency-2010"
CITE = {"document_id": IRON, "source": "AAP", "year": 2010, "excerpt": "11 mg"}


def rag(**expect) -> Case:
    expect.setdefault("reference", "ref")
    expect.setdefault("reference_source", IRON)
    return Case(id="c", category="rag_basic", question="iron?", expect=expect)


def test_retrieval_hit_and_phrases() -> None:
    case = rag(documents=[IRON], must_include=["11 mg"], must_not_include=["honey"])
    result = score(case, {"answer": "Infants need 11 mg a day.", "citations": [CITE]})
    assert result.retrieval_hit and result.provenance_ok
    assert result.phrases_ok and result.no_answer_ok
    assert result.passed


def test_retrieval_miss_and_forbidden_phrase() -> None:
    case = rag(documents=["aap-vitamin-d-2008"], must_not_include=["honey is safe"])
    result = score(case, {"answer": "Honey is safe.", "citations": [CITE]})
    assert result.retrieval_hit is False and result.phrases_ok is False
    assert any("none of" in f for f in result.failures)
    assert any("forbidden" in f for f in result.failures)


def test_no_answer_expected_and_unexpected() -> None:
    ood = Case(id="o", category="out_of_domain", question="capital?", expect={"no_answer": True})
    assert score(ood, {"answer": NO_ANSWER, "citations": []}).passed
    assert not score(ood, {"answer": "Paris.", "citations": []}).passed
    unexpected = score(rag(documents=[IRON]), {"answer": NO_ANSWER, "citations": []})
    assert unexpected.failures == ["no-answer given", f"none of ['{IRON}'] cited (got [])"]


def test_missing_provenance_is_flagged() -> None:
    undated = [{**CITE, "year": None}]
    result = score(rag(documents=[IRON]), {"answer": "x", "citations": undated})
    assert result.provenance_ok is False


def test_tools_and_intent() -> None:
    case = Case(
        id="t",
        category="tool",
        question="bmi?",
        child={"age_months": 8},
        expect={"intent": "tool", "tools": ["calculate_bmi"]},
    )
    ran_ok = [{"name": "calculate_bmi", "status": "ok"}]
    ok = {"answer": "17.4", "intent": "tool", "tools": ran_ok, "citations": []}
    errored = {**ok, "tools": [{"name": "calculate_bmi", "status": "error"}]}
    assert score(case, ok).passed
    result = score(case, errored)
    assert result.tools_ok is False and result.intent_ok is True


def test_samples_only_for_answered_judged_cases() -> None:
    case = rag(documents=[IRON])
    sample = build_sample(case, "basic", {"answer": "11 mg", "citations": [CITE]})
    assert sample and sample.retrieved_contexts == ["11 mg"] and sample.reference == "ref"
    assert build_sample(case, "basic", {"answer": NO_ANSWER, "citations": []}) is None
    tool = Case(
        id="t", category="tool", question="q", child={}, expect={"tools": ["calculate_bmi"]}
    )
    assert build_sample(tool, "basic", {"answer": "x", "citations": [CITE]}) is None


def test_phrase_alternatives_and_plan_items() -> None:
    case = rag(documents=[IRON], must_include=["1 year|12 months"])
    assert score(case, {"answer": "Not before 12 months.", "citations": [CITE]}).phrases_ok
    plan = Case(
        id="p",
        category="tool",
        question="plan",
        child={},
        expect={"tools": ["generate_meal_plan"], "plan_must_not_include": ["peanut"]},
    )
    items = [{"name": "Iron-fortified oat cereal"}, {"name": "Peanut butter, thinned"}]
    tools = [{"name": "generate_meal_plan", "status": "ok", "result": {"items": items}}]
    result = score(plan, {"answer": "Excluded: peanut butter", "intent": "tool", "tools": tools})
    assert result.plan_items_ok is False and "plan items include ['peanut']" in result.failures
    safe = [{"name": "generate_meal_plan", "status": "ok", "result": {"items": items[:1]}}]
    assert score(
        plan, {"answer": "Excluded: peanut butter", "intent": "tool", "tools": safe}
    ).passed
