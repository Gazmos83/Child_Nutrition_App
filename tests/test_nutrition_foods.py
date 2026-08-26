"""Food table loading and validation (tasks 1.2, 1.3; food-composition-data spec)."""

from pathlib import Path

import pytest
import yaml

from backend.nutrition.foods import (
    DEFAULT_FOOD_TABLE_PATH,
    FoodCategory,
    FoodNotFoundError,
    load_food_table,
)

VALID_ENTRY = {
    "id": "banana",
    "name": "Banana, mashed",
    "category": "fruit",
    "serving_size": 50,
    "serving_unit": "g",
    "calories": 45,
    "protein_g": 0.5,
    "fat_g": 0.2,
    "carbohydrate_g": 11.4,
    "iron_mg": 0.1,
    "calcium_mg": 2.5,
    "allergens": [],
    "choking_hazard": False,
    "contains_honey": False,
    "commonly_unpasteurized": False,
    "min_age_months": 6,
}


def write_table(tmp_path: Path, *foods: dict) -> Path:
    path = tmp_path / "foods.yaml"
    table = {"version": "test", "source": "test source", "foods": list(foods)}
    path.write_text(yaml.safe_dump(table))
    return path


class TestLoading:
    def test_valid_table_loads(self, tmp_path: Path) -> None:
        table = load_food_table(write_table(tmp_path, VALID_ENTRY))
        food = table.get("banana")
        assert food.calories == 45
        assert food.category is FoodCategory.FRUIT
        assert food.allergens == frozenset()
        assert table.source_for(food) == "test source"
        assert len(table) == 1

    def test_entry_source_overrides_table_source(self, tmp_path: Path) -> None:
        table = load_food_table(write_table(tmp_path, {**VALID_ENTRY, "source": "label"}))
        assert table.source_for(table.get("banana")) == "label"

    def test_unknown_id_raises_not_found(self, tmp_path: Path) -> None:
        table = load_food_table(write_table(tmp_path, VALID_ENTRY))
        with pytest.raises(FoodNotFoundError, match="bananas"):
            table.get("bananas")
        assert "bananas" not in table

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_food_table(tmp_path / "absent.yaml")


class TestValidationFailsWhole:
    def test_negative_calories_names_entry(self, tmp_path: Path) -> None:
        path = write_table(tmp_path, VALID_ENTRY, {**VALID_ENTRY, "id": "bad", "calories": -1})
        with pytest.raises(ValueError, match=r"foods\[1\] \(bad\)\.calories"):
            load_food_table(path)

    def test_unknown_allergen_names_entry(self, tmp_path: Path) -> None:
        path = write_table(tmp_path, {**VALID_ENTRY, "allergens": ["gluten"]})
        with pytest.raises(ValueError, match=r"foods\[0\] \(banana\)\.allergens"):
            load_food_table(path)

    def test_missing_required_field_names_entry(self, tmp_path: Path) -> None:
        entry = dict(VALID_ENTRY)
        del entry["contains_honey"]
        with pytest.raises(ValueError, match=r"\(banana\)\.contains_honey"):
            load_food_table(write_table(tmp_path, entry))

    def test_age_outside_range_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="min_age_months"):
            load_food_table(write_table(tmp_path, {**VALID_ENTRY, "min_age_months": 61}))

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="sugar_g"):
            load_food_table(write_table(tmp_path, {**VALID_ENTRY, "sugar_g": 3}))

    def test_duplicate_id_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="listed twice"):
            load_food_table(write_table(tmp_path, VALID_ENTRY, VALID_ENTRY))

    def test_empty_table_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "foods.yaml"
        path.write_text(yaml.safe_dump({"version": "t", "source": "s", "foods": []}))
        with pytest.raises(ValueError):
            load_food_table(path)


# Foods the AAP choking-prevention statement (2010) lists for children under 4.
CHOKING_LIST = {"whole_grapes", "whole_nuts", "popcorn", "hot_dog", "hard_candy"}
# Products the CDC food-safety guidance says never to give young children.
UNPASTEURIZED_LIST = {"raw_milk_soft_cheese", "unpasteurized_juice"}
HONEY_LIST = {"honey"}


@pytest.fixture(scope="module")
def table():
    return load_food_table(DEFAULT_FOOD_TABLE_PATH)


class TestCommittedTable:
    def test_committed_table_loads(self, table) -> None:
        assert 30 <= len(table) <= 60
        assert table.version

    def test_known_unsafe_foods_flagged(self, table) -> None:
        for food_id in HONEY_LIST:
            assert table.get(food_id).contains_honey, food_id
        for food_id in CHOKING_LIST:
            assert table.get(food_id).choking_hazard, food_id
        for food_id in UNPASTEURIZED_LIST:
            assert table.get(food_id).commonly_unpasteurized, food_id

    def test_only_milk_feeds_under_six_months(self, table) -> None:
        for food in table.foods:
            if food.category is FoodCategory.MILK_FEED:
                assert food.min_age_months == 0, food.id
            else:
                assert food.min_age_months >= 6, food.id

    def test_cows_milk_as_drink_from_twelve_months(self, table) -> None:
        assert table.get("whole_cows_milk").min_age_months == 12

    def test_every_entry_names_a_source_and_required_nutrients(self, table) -> None:
        for food in table.foods:
            assert table.source_for(food).strip(), food.id
            assert food.calories >= 0 and food.protein_g >= 0 and food.iron_mg >= 0

    def test_allergen_flags_present_on_obvious_foods(self, table) -> None:
        assert "peanut" in {a.value for a in table.get("peanut_butter_thinned").allergens}
        assert "milk" in {a.value for a in table.get("whole_cows_milk").allergens}
        assert "egg" in {a.value for a in table.get("egg_scrambled").allergens}
        assert "fish" in {a.value for a in table.get("salmon_cooked").allergens}

    def test_plan_has_variety_available_for_a_vegan_infant(self, table) -> None:
        """Enough plant, allergen-free, non-hazard solids exist that a vegan 9-month-old
        with a peanut allergy is not left with an empty table."""
        eligible = [
            f
            for f in table.foods
            if f.category
            in {FoodCategory.GRAIN, FoodCategory.VEGETABLE, FoodCategory.FRUIT, FoodCategory.LEGUME}
            and not f.allergens
            and not f.choking_hazard
            and not f.contains_honey
            and f.min_age_months <= 9
        ]
        assert len(eligible) >= 8
