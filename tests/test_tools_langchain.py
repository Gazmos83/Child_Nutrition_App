"""StructuredTool wrappers expose the tools with typed schemas (Day 4 6.1; change 2 3.4)."""

import socket

import pytest
from pydantic import ValidationError

from backend.schemas.tools import BmiResult, LoggedFeeding, MealPlanResult, NutrientGapReport
from backend.tools.langchain_tools import build_tools

EXPECTED_NAMES = {
    "calculate_bmi",
    "calculate_calorie_target",
    "calculate_protein_target",
    "lookup_food",
    "calculate_meal_nutrition",
    "generate_meal_plan",
    # Change 2: the feeding log.
    "log_feeding",
    "get_daily_nutrition",
    "get_remaining_targets",
    "detect_nutrient_gaps",
}


@pytest.fixture
def tools():
    return {t.name: t for t in build_tools(None)}


def test_ten_tools_with_unique_names_and_schemas(tools) -> None:
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
    assert len(build_tools(None)) == len(EXPECTED_NAMES)


def test_log_feeding_rejects_zero_quantity_before_running(tools) -> None:
    with pytest.raises(ValidationError):
        tools["log_feeding"].invoke(
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 0}
        )


def test_log_feeding_returns_priced_entry(tools) -> None:
    logged = tools["log_feeding"].invoke(
        {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 150}
    )
    assert isinstance(logged, LoggedFeeding)
    assert logged.entry.id and logged.nutrients.calories == 100.5


def test_daily_nutrition_over_an_empty_log(tools) -> None:
    result = tools["get_daily_nutrition"].invoke({"timezone": "Europe/Vilnius"})
    assert result.totals.calories == 0 and result.timezone == "Europe/Vilnius"


async def test_remaining_targets_and_gaps_are_async_only(tools) -> None:
    child = {"age_months": 8, "weight_kg": 8.5, "sex": "female", "as_of": "2026-08-27"}
    report = await tools["detect_nutrient_gaps"].ainvoke(child)
    assert isinstance(report, NutrientGapReport) and report.status == "insufficient_data"
    remaining = await tools["get_remaining_targets"].ainvoke(
        {"age_months": 8, "weight_kg": 8.5, "sex": "female", "date": "2026-08-27"}
    )
    assert remaining.remaining.calories == 678.0
    with pytest.raises(NotImplementedError):
        tools["detect_nutrient_gaps"].invoke(child)
