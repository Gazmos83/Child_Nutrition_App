"""Food lookup and meal nutrition over the table (task 2.2)."""

import subprocess

import pytest

from backend.nutrition.foods import FoodNotFoundError, load_food_table
from backend.schemas.tools import FoodLookupInput, MealItem, MealNutritionInput
from backend.tools.nutrient_tools import calculate_meal_nutrition, lookup_food
from tests.test_nutrition_foods import VALID_ENTRY, write_table

LENTILS = {
    **VALID_ENTRY,
    "id": "lentils",
    "name": "Lentils",
    "category": "legume",
    "calories": 58,
    "protein_g": 4.5,
    "fat_g": 0.2,
    "carbohydrate_g": 10.0,
    "iron_mg": 1.7,
    "calcium_mg": 9,
}


@pytest.fixture
def table(tmp_path):
    return load_food_table(write_table(tmp_path, VALID_ENTRY, LENTILS))


class TestLookupFood:
    def test_returns_nutrients_safety_and_source(self, table) -> None:
        record = lookup_food(FoodLookupInput(food_id="lentils"), table)
        assert record.calories == 58 and record.iron_mg == 1.7
        assert record.choking_hazard is False and record.contains_honey is False
        assert record.min_age_months == 6
        assert record.resolved_source == "test source"

    def test_near_miss_names_resolve(self, table) -> None:
        for spoken in ("lentil", "Lentils", "bananas"):
            record = lookup_food(FoodLookupInput(food_id=spoken), table)
            assert record.id in {"lentils", "banana"}

    def test_unknown_id_raises(self, table) -> None:
        with pytest.raises(FoodNotFoundError, match="dragonfruit"):
            lookup_food(FoodLookupInput(food_id="dragonfruit"), table)

    def test_committed_table_by_default(self) -> None:
        record = lookup_food(FoodLookupInput(food_id="whole_cows_milk"))
        assert record.min_age_months == 12
        assert "USDA" in record.resolved_source


class TestResolveCommittedTable:
    """Plain parent language resolves against the real table (food-name-resolution)."""

    @pytest.fixture
    def committed(self):
        return load_food_table()

    @pytest.mark.parametrize(
        ("spoken", "expected"),
        [
            ("bananas", "banana_mashed"),
            ("sweet potatoes", "sweet_potato_mashed"),
            ("sweet potato cooked mashed", "sweet_potato_mashed"),
            ("sweet_potato_cooked_mashed", "sweet_potato_mashed"),  # the regression slug
            ("avocado", "avocado"),  # exact id passes straight through
        ],
    )
    def test_resolves_to_one_food(self, committed, spoken, expected) -> None:
        assert committed.resolve(spoken).id == expected

    def test_danger_entries_resolve_with_flags_intact(self, committed) -> None:
        grapes = committed.resolve("grapes")
        assert grapes.id == "whole_grapes" and grapes.choking_hazard is True
        assert committed.resolve("honey").contains_honey is True

    @pytest.mark.parametrize(
        ("spoken", "expected_ids"),
        [
            ("carrot", {"carrot_cooked_mashed", "raw_carrot_sticks"}),
            ("milk", {"breast_milk", "whole_cows_milk", "plain_whole_yogurt", "raw_milk_soft_cheese"}),
            ("apple", {"apple_cooked", "raw_apple_chunks", "unpasteurized_juice"}),
            ("cheese", {"cheddar_cheese_grated", "cottage_cheese", "raw_milk_soft_cheese"}),
        ],
    )
    def test_ambiguous_name_refuses_and_names_every_candidate(
        self, committed, spoken, expected_ids
    ) -> None:
        with pytest.raises(FoodNotFoundError) as excinfo:
            committed.resolve(spoken)
        suggested_ids = {s.split(" (", 1)[0] for s in excinfo.value.suggestions}
        assert suggested_ids == expected_ids

    def test_unknown_string_is_preserved_with_close_matches(self, committed) -> None:
        with pytest.raises(FoodNotFoundError) as excinfo:
            committed.resolve("banana mashd")
        assert excinfo.value.food_id == "banana mashd"
        assert any("Banana, mashed" in s for s in excinfo.value.suggestions)

    def test_meal_nutrition_counts_a_common_name_and_reports_garbage_as_typed(self) -> None:
        result = calculate_meal_nutrition(
            MealNutritionInput(
                items=[
                    MealItem(food_id="bananas", servings=1),
                    MealItem(food_id="xyzzy", servings=1),
                ]
            )
        )
        assert [i.food_id for i in result.counted] == ["bananas"]
        assert result.missing == ["xyzzy"]
        assert result.totals.calories > 0


class TestMealNutrition:
    def test_sums_scaled_by_servings(self, table) -> None:
        result = calculate_meal_nutrition(
            MealNutritionInput(
                items=[
                    MealItem(food_id="banana", servings=2),
                    MealItem(food_id="lentils", servings=1.5),
                ]
            ),
            table,
        )
        assert result.totals.calories == round(45 * 2 + 58 * 1.5, 1)
        assert result.totals.protein_g == round(0.5 * 2 + 4.5 * 1.5, 1)
        assert result.totals.iron_mg == round(0.1 * 2 + 1.7 * 1.5, 1)
        assert result.totals.calcium_mg == round(2.5 * 2 + 9 * 1.5, 1)
        assert len(result.counted) == 2
        assert result.missing == []
        assert result.source == "test source"

    def test_unknown_food_is_reported_not_dropped_silently(self, table) -> None:
        result = calculate_meal_nutrition(
            MealNutritionInput(
                items=[
                    MealItem(food_id="banana", servings=1),
                    MealItem(food_id="dragonfruit", servings=1),
                ]
            ),
            table,
        )
        assert result.missing == ["dragonfruit"]
        assert [i.food_id for i in result.counted] == ["banana"]
        assert result.totals.calories == 45

    def test_deterministic(self, table) -> None:
        params = MealNutritionInput(items=[MealItem(food_id="lentils", servings=3)])
        assert calculate_meal_nutrition(params, table) == calculate_meal_nutrition(params, table)


def test_nutrition_package_has_no_langchain_dependency() -> None:
    result = subprocess.run(
        ["grep", "-r", "langchain", "backend/nutrition"], capture_output=True, text=True
    )
    assert result.returncode == 1, result.stdout
