"""Infant-safety filter (task 3.1; infant-safety-filter spec)."""

import inspect

import pytest

from backend.models.enums import Allergen
from backend.nutrition.foods import FoodCategory, FoodItem
from backend.nutrition.safety import (
    CHOKING_HAZARD_MIN_AGE_MONTHS,
    HONEY_MIN_AGE_MONTHS,
    UnsafePlanError,
    assert_plan_safe,
    check_food,
    filter_foods,
)


def food(food_id: str = "f", **overrides) -> FoodItem:
    base = dict(
        id=food_id,
        name=food_id,
        category=FoodCategory.FRUIT,
        serving_size=50,
        serving_unit="g",
        calories=40,
        protein_g=1,
        fat_g=0.1,
        carbohydrate_g=9,
        iron_mg=0.2,
        calcium_mg=5,
        allergens=frozenset(),
        choking_hazard=False,
        contains_honey=False,
        commonly_unpasteurized=False,
        min_age_months=6,
    )
    return FoodItem(**{**base, **overrides})


HONEY = food("honey", contains_honey=True, category=FoodCategory.SWEETENER)
GRAPES = food("whole_grapes", choking_hazard=True)
RAW_CHEESE = food("raw_cheese", commonly_unpasteurized=True, allergens={Allergen.MILK})
PEANUT = food("peanut_butter", allergens={Allergen.PEANUT}, category=FoodCategory.NUT_SEED)
COWS_MILK = food("cows_milk", min_age_months=12, allergens={Allergen.MILK})
SAFE = food("banana")


def rules(f: FoodItem, age: int, allergens=()) -> set[str]:
    return {v.rule for v in check_food(f, age, allergens)}


class TestHoney:
    @pytest.mark.parametrize("age", [0, 9, 11])
    def test_excluded_under_twelve_months(self, age: int) -> None:
        assert "no_honey_under_12_months" in rules(HONEY, age)

    @pytest.mark.parametrize("age", [12, 24, 60])
    def test_permitted_from_twelve_months(self, age: int) -> None:
        assert check_food(HONEY, age, ()) == []

    def test_threshold_constant(self) -> None:
        assert HONEY_MIN_AGE_MONTHS == 12


class TestChokingHazard:
    @pytest.mark.parametrize("age", [6, 24, 47])
    def test_excluded_under_four_years(self, age: int) -> None:
        assert "no_choking_hazard_under_4_years" in rules(GRAPES, age)

    @pytest.mark.parametrize("age", [48, 60])
    def test_permitted_from_four_years(self, age: int) -> None:
        assert check_food(GRAPES, age, ()) == []

    def test_threshold_constant(self) -> None:
        assert CHOKING_HAZARD_MIN_AGE_MONTHS == 48


class TestUnpasteurized:
    @pytest.mark.parametrize("age", [0, 12, 36, 60])
    def test_excluded_at_every_age(self, age: int) -> None:
        assert "no_unpasteurized_products" in rules(RAW_CHEESE, age)


class TestAllergens:
    def test_recorded_allergen_excludes_food(self) -> None:
        violations = check_food(PEANUT, 24, {Allergen.PEANUT})
        assert [v.rule for v in violations] == ["no_recorded_allergen"]
        assert "peanut" in violations[0].detail

    def test_other_allergen_does_not(self) -> None:
        assert check_food(PEANUT, 24, {Allergen.MILK}) == []

    def test_accepts_any_iterable(self) -> None:
        assert rules(PEANUT, 24, [Allergen.PEANUT, Allergen.EGG]) == {"no_recorded_allergen"}


class TestMinimumAge:
    def test_below_minimum_age_excluded(self) -> None:
        assert rules(COWS_MILK, 9) == {"below_minimum_age"}

    def test_at_minimum_age_allowed(self) -> None:
        assert check_food(COWS_MILK, 12, ()) == []

    def test_solid_under_six_months_excluded(self) -> None:
        assert rules(SAFE, 4) == {"below_minimum_age"}


class TestMultipleViolations:
    def test_all_reasons_reported(self) -> None:
        bad = food(
            "bad",
            contains_honey=True,
            choking_hazard=True,
            commonly_unpasteurized=True,
            allergens={Allergen.MILK},
            min_age_months=12,
        )
        assert rules(bad, 9, {Allergen.MILK}) == {
            "no_honey_under_12_months",
            "no_choking_hazard_under_4_years",
            "no_unpasteurized_products",
            "no_recorded_allergen",
            "below_minimum_age",
        }


class TestFilterFoods:
    def test_partitions_with_reasons(self) -> None:
        safe, excluded = filter_foods(
            [SAFE, HONEY, GRAPES, RAW_CHEESE, PEANUT], 9, {Allergen.PEANUT}
        )
        assert [f.id for f in safe] == ["banana"]
        assert {e.food.id: e.reasons for e in excluded}.keys() == {
            "honey",
            "whole_grapes",
            "raw_cheese",
            "peanut_butter",
        }
        assert all(e.reasons for e in excluded)

    def test_preserves_order(self) -> None:
        safe, _ = filter_foods([food("b"), food("a"), food("c")], 12, ())
        assert [f.id for f in safe] == ["b", "a", "c"]

    def test_empty_input(self) -> None:
        assert filter_foods([], 12, ()) == ([], [])


class TestAssertPlanSafe:
    def test_passes_for_safe_plan(self) -> None:
        assert_plan_safe([SAFE, COWS_MILK], 12, ())

    def test_raises_on_planted_violation(self) -> None:
        with pytest.raises(UnsafePlanError, match="honey"):
            assert_plan_safe([SAFE, HONEY], 9, ())

    def test_raises_on_allergen(self) -> None:
        with pytest.raises(UnsafePlanError, match="peanut"):
            assert_plan_safe([PEANUT], 24, {Allergen.PEANUT})


class TestNoBypass:
    """The functions expose nothing that could weaken a rule (spec: no override path)."""

    @pytest.mark.parametrize("fn", [check_food, filter_foods, assert_plan_safe])
    def test_signature_has_only_food_age_and_allergens(self, fn) -> None:
        params = list(inspect.signature(fn).parameters)
        assert params[1:] == ["age_months", "allergens"], params
        assert all(
            p.default is inspect.Parameter.empty for p in inspect.signature(fn).parameters.values()
        )

    def test_module_imports_no_model_or_rag_code(self) -> None:
        import backend.nutrition.safety as module

        source = inspect.getsource(module)
        assert "langchain" not in source
        assert "backend.rag" not in source
