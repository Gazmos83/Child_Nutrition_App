"""``ChatRequest`` and friends validate before any work (Day 5 task 2.1; chat-api spec)."""

import pytest
from pydantic import ValidationError

from backend.schemas.chat import ChatRequest, ChatTurn, ChildContext, ToolActivity

CHILD = {"age_months": 8, "weight_kg": 8.5, "sex": "female"}


def test_minimal_message_is_accepted_with_defaults() -> None:
    request = ChatRequest.model_validate({"message": "hi"})
    assert request.message == "hi"
    assert request.child is None
    assert request.history == []
    assert request.strategy == "advanced"
    assert request.stream is True


def test_message_is_stripped() -> None:
    assert ChatRequest.model_validate({"message": "  iron?  "}).message == "iron?"


@pytest.mark.parametrize(
    "body",
    [
        {"message": "   "},
        {},
        {"message": "x" * 2001},
        {"message": "hi", "user_id": "abc"},
        {"message": "hi", "strategy": "hybrid"},
        {"message": "hi", "history": [{"role": "user", "content": "q"}] * 13},
        {"message": "hi", "history": [{"role": "system", "content": "q"}]},
        {"message": "hi", "child": {**CHILD, "age_months": 61}},
        {"message": "hi", "child": {**CHILD, "weight_kg": 0}},
        {"message": "hi", "child": {**CHILD, "allergies": ["gluten"]}},
        {"message": "hi", "child": {**CHILD, "age_months": 40}},
        {"message": "hi", "child": {**CHILD, "diet_preference": "keto"}},
        {"message": "hi", "child": {**CHILD, "nickname": "bean"}},
    ],
)
def test_invalid_requests_are_rejected(body: dict) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(body)


def test_twelve_turns_are_accepted() -> None:
    turns = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}] * 6
    assert len(ChatRequest.model_validate({"message": "hi", "history": turns}).history) == 12


def test_child_context_matches_meal_plan_input_rules() -> None:
    child = ChildContext.model_validate(
        {**CHILD, "allergies": ["peanut", "peanut"], "doctors_note": "   "}
    )
    assert child.allergies == frozenset({"peanut"})
    assert child.doctors_note is None  # blank note normalised away
    assert child.diet_preference == "omnivore"
    older = ChildContext.model_validate({**CHILD, "age_months": 40, "height_cm": 100})
    assert older.height_cm == 100


def test_child_context_is_frozen() -> None:
    child = ChildContext.model_validate(CHILD)
    with pytest.raises(ValidationError):
        child.age_months = 9  # type: ignore[misc]


def test_tool_activity_defaults() -> None:
    activity = ToolActivity(name="calculate_bmi", status="ok", result={"bmi": 17.36})
    assert activity.used_context == [] and activity.error is None and activity.detail is None
    assert ChatTurn(role="user", content="x").role == "user"
