import datetime as dt
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.cases import Case, CaseSet, FeedFixture, load_cases

CASES = Path(__file__).resolve().parents[1] / "cases.yaml"


def test_real_file_loads_and_resolves_fixtures() -> None:
    case_set = load_cases(CASES)
    assert 40 <= len(case_set.cases) <= 60
    tool_case = next(c for c in case_set.cases if c.id == "tool-bmi")
    assert tool_case.child and tool_case.child["age_months"] == 8
    logged = next(c for c in case_set.cases if c.id == "user-gaps")
    assert len(logged.feeding_log) == 10 and logged.endpoint == "chat"
    assert next(c for c in case_set.cases if c.id == "rag-iron-8mo").endpoint == "ask"


def test_unknown_category_and_duplicate_id_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Case(id="x", category="riddles", question="q", expect={})
    with pytest.raises(ValidationError, match="duplicate"):
        CaseSet(
            cases=[
                Case(id="a", category="out_of_domain", question="q", expect={"no_answer": True}),
                Case(id="a", category="out_of_domain", question="q2", expect={"no_answer": True}),
            ]
        )


def test_chat_cases_need_a_child_and_judged_cases_a_reference() -> None:
    with pytest.raises(ValidationError, match="child fixture"):
        Case(id="t", category="tool", question="q", expect={"tools": ["calculate_bmi"]})
    with pytest.raises(ValidationError, match="reference"):
        Case(id="r", category="rag_basic", question="q", expect={"documents": ["x"]})


def test_feed_fixture_resolves_relative_to_now() -> None:
    now = dt.datetime(2026, 8, 28, 15, 0, tzinfo=dt.UTC)
    feed = FeedFixture(days_ago=2, time="07:30", feeding_type="formula", quantity=180)
    assert feed.resolve(now) == {
        "fed_at": "2026-08-26T07:30:00+00:00",
        "feeding_type": "formula",
        "unit": "ml",
        "quantity": 180.0,
    }
