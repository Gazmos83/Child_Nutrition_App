"""generate_meal_plan: constraints compose, plans are safe, audited, disclaimed (tasks 5.1-5.3)."""

import json
import logging

import pytest
from pydantic import ValidationError

from backend.models.enums import Allergen, DietPreference, Sex
from backend.nutrition.diet import EXCLUDED_CATEGORIES
from backend.nutrition.foods import FoodCategory, get_food_table, load_food_table
from backend.nutrition.safety import check_food
from backend.rag.prompts import DISCLAIMER
from backend.schemas.tools import MealPlanRequest
from backend.tools.meal_plan import (
    IRON_UL_MG,
    MAX_ITEMS,
    NO_SAFE_PLAN_MESSAGE,
    generate_meal_plan,
)
from tests.fixtures.fake_llm import RecordingChatModel
from tests.test_nutrition_foods import VALID_ENTRY, write_table


def request(**overrides) -> MealPlanRequest:
    base = dict(age_months=9, weight_kg=8.8, sex=Sex.FEMALE)
    return MealPlanRequest(**{**base, **overrides})


async def plan(**overrides):
    return await generate_meal_plan(request(**overrides), None)


def categories_of(result) -> set[FoodCategory]:
    table = get_food_table()
    return {table.get(i.food_id).category for i in result.items}


class TestSafetyAndDietCompose:
    async def test_four_month_plan_is_milk_only(self) -> None:
        result = await plan(age_months=4, weight_kg=6.5)
        assert result.outcome == "plan"
        assert result.items
        assert categories_of(result) == {FoodCategory.MILK_FEED}
        assert all(i.meal == "milk feed" for i in result.items)
        # The milk anchor aims at the whole calorie target before 6 months.
        assert 0.85 <= result.coverage.calories <= 1.15

    async def test_nine_month_plan_has_no_honey_and_nothing_below_min_age(self) -> None:
        result = await plan(age_months=9)
        table = get_food_table()
        for item in result.items:
            food = table.get(item.food_id)
            assert not food.contains_honey, item.food_id
            assert food.min_age_months <= 9, item.food_id
        excluded = {e.food_id for e in result.exclusions}
        assert {"honey", "whole_cows_milk", "unpasteurized_juice"} <= excluded

    async def test_nine_month_plan_anchors_on_milk_and_adds_solids(self) -> None:
        result = await plan(age_months=9)
        cats = categories_of(result)
        assert FoodCategory.MILK_FEED in cats
        assert cats - {FoodCategory.MILK_FEED}, "solids expected from 6 months"
        assert "breast_milk" in {i.food_id for i in result.items}

    async def test_two_year_plan_has_no_choking_hazard_and_no_milk_feed(self) -> None:
        result = await plan(age_months=24, weight_kg=12.5)
        table = get_food_table()
        assert result.items
        for item in result.items:
            assert not table.get(item.food_id).choking_hazard, item.food_id
        assert FoodCategory.MILK_FEED not in categories_of(result)
        assert {"whole_grapes", "popcorn", "hot_dog"} <= {e.food_id for e in result.exclusions}

    @pytest.mark.parametrize(
        ("age", "weight", "height"),
        [
            (0, 3.5, None),
            (6, 7.5, None),
            (11, 9.2, None),
            (18, 11.0, None),
            (36, 14.5, 96.0),
            (60, 18.0, 108.0),
        ],
    )
    async def test_no_plan_at_any_age_contains_an_unpasteurized_food(
        self, age, weight, height
    ) -> None:
        result = await plan(age_months=age, weight_kg=weight, height_cm=height)
        table = get_food_table()
        assert all(not table.get(i.food_id).commonly_unpasteurized for i in result.items)
        # And the finished plan passes the filter outright.
        for item in result.items:
            assert check_food(table.get(item.food_id), age, ()) == []

    async def test_peanut_allergy_excludes_peanut_foods(self) -> None:
        result = await plan(age_months=18, weight_kg=10.5, allergies={Allergen.PEANUT})
        table = get_food_table()
        for item in result.items:
            assert Allergen.PEANUT not in table.get(item.food_id).allergens, item.food_id
        peanut_exclusions = [e for e in result.exclusions if e.food_id == "peanut_butter_thinned"]
        assert peanut_exclusions and "peanut" in peanut_exclusions[0].reasons[0]

    async def test_vegan_child_gets_no_animal_foods(self) -> None:
        result = await plan(age_months=20, weight_kg=11.0, diet_preference=DietPreference.VEGAN)
        assert result.items
        assert categories_of(result).isdisjoint(EXCLUDED_CATEGORIES[DietPreference.VEGAN])
        assert "honey" in {e.food_id for e in result.exclusions}
        egg = [e for e in result.exclusions if e.food_id == "egg_scrambled"]
        assert egg and "vegan" in egg[0].reasons[0]

    async def test_thirty_six_month_request_without_height_rejected_before_anything(self) -> None:
        with pytest.raises(ValidationError, match="height_cm is required"):
            request(age_months=36, weight_kg=14)


class TestPlanShape:
    async def test_every_plan_carries_disclaimer_and_table_version(self) -> None:
        for kwargs in (dict(age_months=2, weight_kg=5), dict(age_months=30, weight_kg=13)):
            result = await plan(**kwargs)
            assert result.disclaimer == DISCLAIMER
            assert result.food_table_version == get_food_table().version

    async def test_deterministic(self) -> None:
        first = await plan(age_months=15, weight_kg=10.2)
        second = await plan(age_months=15, weight_kg=10.2)
        assert first == second

    async def test_bounded_items_and_calories(self) -> None:
        for age, weight, height in ((8, 8.0, None), (24, 12.0, None), (48, 16.0, 102.0)):
            result = await plan(age_months=age, weight_kg=weight, height_cm=height)
            assert 1 <= len(result.items) <= MAX_ITEMS
            assert result.coverage.calories <= 1.1
            assert result.totals.calories > 0

    @pytest.mark.parametrize(
        ("age", "weight", "height"),
        [(9, 8.8, None), (24, 12.5, None), (36, 14.5, 96.0), (48, 16.0, 102.0), (60, 18.0, 108.0)],
    )
    async def test_iron_never_exceeds_upper_intake_level(self, age, weight, height) -> None:
        result = await plan(age_months=age, weight_kg=weight, height_cm=height)
        assert result.totals.iron_mg <= IRON_UL_MG
        # Once the target is met the top-up must not keep chasing iron.
        assert result.coverage.iron <= 3.0, result.coverage

    async def test_composer_never_recommends_hazards_or_sweeteners_even_when_permitted(
        self,
    ) -> None:
        """At 48-60 months the filter permits choking-list foods and honey; the composer
        still never picks them (design Decision 9)."""
        table = get_food_table()
        for age, weight, height in ((48, 16.0, 102.0), (60, 18.0, 108.0)):
            result = await plan(age_months=age, weight_kg=weight, height_cm=height)
            for item in result.items:
                food = table.get(item.food_id)
                assert not food.choking_hazard, item.food_id
                assert food.category is not FoodCategory.SWEETENER, item.food_id
            assert "hot_dog" not in {e.food_id for e in result.exclusions}  # permitted, not chosen

    async def test_top_up_diversifies_once_targets_met(self) -> None:
        result = await plan(age_months=24, weight_kg=12.5)
        assert len(result.items) >= 6
        assert any("targets already met" in i.reason for i in result.items)

    async def test_totals_match_nutrient_tool_over_items(self) -> None:
        result = await plan(age_months=24, weight_kg=12.5)
        table = get_food_table()
        expected = sum(table.get(i.food_id).calories * i.servings for i in result.items)
        assert result.totals.calories == round(expected, 1)

    async def test_no_note_means_no_override(self) -> None:
        result = await plan()
        assert result.note_extraction.status == "not_present"
        assert result.override.conflict is False
        assert result.override.source == "general_target"

    async def test_note_without_model_is_flagged_unparsed_and_plan_still_generated(self) -> None:
        result = await plan(doctors_note="Limit to 650 kcal per day.")
        assert result.outcome == "plan"
        assert result.note_extraction.status == "unparsed"
        assert result.override.conflict is False


class TestComposedConstraints:
    async def test_all_four_constraints_compose(self) -> None:
        llm = RecordingChatModel(
            responses=[
                '{"nutrient": "calories", "direction": "max", "value": 650, "unit": "kcal"}'
            ],
            calls=[],
        )
        result = await generate_meal_plan(
            request(
                age_months=8,
                weight_kg=8.5,
                diet_preference=DietPreference.VEGETARIAN,
                allergies={Allergen.PEANUT},
                doctors_note="Please limit intake to 650 kcal per day.",
            ),
            llm,
        )
        table = get_food_table()
        assert result.outcome == "plan"
        # Doctor's note wins on conflict: general 89*8.5-100+22 = 678 > 650.
        assert result.override.conflict is True
        assert result.override.general_value == 678
        assert result.targets.calories.calories == 650
        assert result.note_extraction.status == "applied"
        # Allergen, diet, and safety all honoured.
        for item in result.items:
            food = table.get(item.food_id)
            assert Allergen.PEANUT not in food.allergens
            assert food.category not in EXCLUDED_CATEGORIES[DietPreference.VEGETARIAN]
            assert not food.contains_honey
            assert food.min_age_months <= 8
        # The note text reached the model exactly once.
        assert len(llm.calls) == 1 and "650 kcal" in llm.calls[0][1].content

    async def test_no_safe_plan_when_nothing_is_eligible(self, tmp_path) -> None:
        table = load_food_table(
            write_table(
                tmp_path,
                {**VALID_ENTRY, "id": "tofu", "category": "legume", "allergens": ["soy"]},
                {**VALID_ENTRY, "id": "bread", "category": "grain", "allergens": ["wheat"]},
                {**VALID_ENTRY, "id": "yogurt", "category": "dairy", "allergens": ["milk"]},
                {**VALID_ENTRY, "id": "honey", "category": "sweetener", "contains_honey": True},
            )
        )
        result = await generate_meal_plan(
            request(
                age_months=15,
                weight_kg=10,
                diet_preference=DietPreference.VEGAN,
                allergies={Allergen.SOY, Allergen.WHEAT},
            ),
            None,
            table,
        )
        assert result.outcome == "no_safe_plan"
        assert result.items == []
        assert result.totals.calories == 0
        assert result.message == NO_SAFE_PLAN_MESSAGE
        assert {e.food_id for e in result.exclusions} == {"tofu", "bread", "yogurt", "honey"}
        assert result.disclaimer == DISCLAIMER


def audit_records(caplog) -> list[dict]:
    out = []
    for record in caplog.records:
        if record.name == "backend.tools.audit" and record.getMessage().startswith(
            "meal_plan_audit "
        ):
            out.append(json.loads(record.getMessage().removeprefix("meal_plan_audit ")))
    return out


class TestAuditLog:
    async def test_plan_outcome_logs_full_snapshot(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        result = await plan(
            age_months=9,
            weight_kg=8.8,
            allergies={Allergen.EGG},
            doctors_note="Limit to 650 kcal per day.",
        )
        [record] = audit_records(caplog)
        assert record["outcome"] == "plan"
        assert record["input"] == {
            "age_months": 9,
            "weight_kg": 8.8,
            "height_cm": None,
            "sex": "female",
            "diet_preference": "omnivore",
            "allergies": ["egg"],
            "doctors_note": "Limit to 650 kcal per day.",
            "activity_level": "low_active",
        }
        assert record["note_extraction"]["status"] == "unparsed"
        for key in ("calories", "protein_g", "iron_mg"):
            assert record["targets"][key]["source"] and record["targets"][key]["band"]
        assert record["override"]["conflict"] is False
        assert {e["food_id"] for e in record["exclusions"]} >= {"honey", "egg_scrambled"}
        assert [i["food_id"] for i in record["items"]] == [i.food_id for i in result.items]
        assert record["totals"]["calories"] == result.totals.calories
        assert record["food_table_version"] == result.food_table_version
        assert "no_honey_under_12_months" in record["rules"]

    async def test_no_safe_plan_outcome_is_logged_too(self, caplog, tmp_path) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        table = load_food_table(
            write_table(tmp_path, {**VALID_ENTRY, "id": "grapes", "choking_hazard": True})
        )
        await generate_meal_plan(request(age_months=24, weight_kg=12), None, table)
        [record] = audit_records(caplog)
        assert record["outcome"] == "no_safe_plan"
        assert record["items"] == []
        assert record["input"]["age_months"] == 24
        assert record["exclusions"][0]["food_id"] == "grapes"
        assert "choking" in record["exclusions"][0]["reasons"][0]
