"""StructuredTool wrappers expose the six tools with typed schemas (task 6.1)."""

import socket

import pytest
from pydantic import ValidationError

from backend.schemas.tools import BmiResult, MealPlanResult
from backend.tools.langchain_tools import build_tools

EXPECTED_NAMES = {
    "calculate_bmi",
    "calculate_calorie_target",
    "calculate_protein_target",
    "lookup_food",
    "calculate_meal_nutrition",
    "generate_meal_plan",
}


@pytest.fixture
def tools():
    return {t.name: t for t in build_tools(None)}


def test_six_tools_with_unique_names_and_schemas(tools) -> None:
    assert set(tools) == EXPECTED_NAMES
    assert len(build_tools(None)) == len(EXPECTED_NAMES)
    for tool in tools.values():
        assert tool.args_schema is not None, tool.name
        assert tool.description, tool.name
        assert tool.args  # JSON-schema properties for the model


def test_bmi_invoke_returns_rounded_value(tools) -> None:
    result = tools["calculate_bmi"].invoke({"weight_kg": 9.0, "height_cm": 72.0})
    assert isinstance(result, BmiResult)
    assert result.bmi == 17.36


def test_invalid_arguments_rejected_by_schema(tools) -> None:
    with pytest.raises(ValidationError):
        tools["calculate_protein_target"].invoke({"age_months": 72, "weight_kg": 20})


def test_lookup_and_meal_nutrition(tools) -> None:
    food = tools["lookup_food"].invoke({"food_id": "lentils_cooked"})
    assert food.iron_mg == 1.7
    meal = tools["calculate_meal_nutrition"].invoke(
        {
            "items": [
                {"food_id": "lentils_cooked", "servings": 2},
                {"food_id": "nope", "servings": 1},
            ]
        }
    )
    assert meal.totals.iron_mg == 3.4
    assert meal.missing == ["nope"]


async def test_meal_plan_ainvoke_returns_result(tools) -> None:
    result = await tools["generate_meal_plan"].ainvoke(
        {"age_months": 10, "weight_kg": 9.0, "sex": "male", "allergies": ["milk"]}
    )
    assert isinstance(result, MealPlanResult)
    assert result.outcome == "plan"
    assert result.disclaimer


def test_meal_plan_has_no_sync_path(tools) -> None:
    with pytest.raises(NotImplementedError):
        tools["generate_meal_plan"].invoke({"age_months": 10, "weight_kg": 9.0, "sex": "male"})


def test_building_tools_is_offline(monkeypatch) -> None:
    def no_network(*args, **kwargs):
        raise AssertionError("network access while building tools")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert len(build_tools(None)) == 6
