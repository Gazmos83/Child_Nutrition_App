"""generate_meal_plan: constraints compose, plans are safe, audited, disclaimed (tasks 5.1-5.3)."""

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.chat import copy as chat_copy
from backend.chat.copy import TARGETS_MET_MESSAGE
from backend.models.enums import Allergen, DietPreference, FeedingType, NoteKind, Sex
from backend.nutrition.diet import EXCLUDED_CATEGORIES
from backend.nutrition.foods import FoodCategory, get_food_table, load_food_table
from backend.nutrition.safety import check_food
from backend.rag.prompts import DISCLAIMER
from backend.schemas.tools import (
    FeedingEntry,
    MealPlanRequest,
    NoteRow,
    NutrientGap,
    NutrientGapReport,
)
from backend.tools.meal_plan import (
    IRON_UL_MG,
    MAX_ITEMS,
    NO_SAFE_PLAN_MESSAGE,
    generate_meal_plan,
)
from backend.tools.targets_resolution import general_targets
from tests.fixtures.fake_llm import RecordingChatModel
from tests.test_nutrition_foods import VALID_ENTRY, write_table


def request(**overrides) -> MealPlanRequest:
    base = dict(age_months=9, weight_kg=8.8, sex=Sex.FEMALE)
    return MealPlanRequest(**{**base, **overrides})


async def plan(**overrides):
    return await generate_meal_plan(request(**overrides), None)


def doctor(text: str) -> NoteRow:
    return NoteRow(kind=NoteKind.DOCTOR, text=text)


def preference(text: str) -> NoteRow:
    return NoteRow(kind=NoteKind.PREFERENCE, text=text)


def note_reply(*rows: dict) -> str:
    return json.dumps({"rows": list(rows)})


CALORIES_650 = {"nutrient": "calories", "direction": "max", "value": 650, "unit": "kcal"}


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
        assert result.overrides == [] and result.note_outcomes == []

    async def test_note_without_model_is_flagged_unparsed_and_plan_still_generated(self) -> None:
        result = await plan(notes=[doctor("Limit to 650 kcal per day.")])
        assert result.outcome == "plan"
        assert result.note_extraction.status == "unparsed"
        assert result.overrides == []
        [outcome] = result.note_outcomes
        assert outcome.applied is False and outcome.detail == chat_copy.NOTE_EXTRACTION_UNAVAILABLE


class TestComposedConstraints:
    async def test_all_four_constraints_compose(self) -> None:
        llm = RecordingChatModel(
            responses=[note_reply({"row": 1, "target": CALORIES_650, "avoid": []})],
            calls=[],
        )
        result = await generate_meal_plan(
            request(
                age_months=8,
                weight_kg=8.5,
                diet_preference=DietPreference.VEGETARIAN,
                allergies={Allergen.PEANUT},
                notes=[doctor("Please limit intake to 650 kcal per day.")],
            ),
            llm,
        )
        table = get_food_table()
        assert result.outcome == "plan"
        # Doctor's note wins on conflict: general 89*8.5-100+22 = 678 > 650.
        [override] = result.overrides
        assert override.conflict is True
        assert override.general_value == 678
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
            notes=[doctor("Limit to 650 kcal per day.")],
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
            "notes": [{"kind": "doctor", "text": "Limit to 650 kcal per day."}],
            "activity_level": "low_active",
        }
        assert record["note_extraction"]["status"] == "unparsed"
        for key in ("calories", "protein_g", "iron_mg"):
            assert record["targets"][key]["source"] and record["targets"][key]["band"]
        assert record["overrides"] == [] and record["avoidances"] == []
        assert record["note_outcomes"][0]["applied"] is False
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


# -- Change 2: feeding log inputs (tasks 3.1-3.3) -------------------------------------------

FIXTURE = Path("tests") / "fixtures" / "meal_plans_before_change_2.json"
NEW_RESULT_FIELDS = {"adjustments", "already_logged"}
DAY = date(2026, 8, 27)


def cereal_today(grams: float, hour: int = 8) -> FeedingEntry:
    return FeedingEntry(
        fed_at=datetime(DAY.year, DAY.month, DAY.day, hour, 0, tzinfo=UTC),
        feeding_type=FeedingType.SOLID,
        food_id="infant_cereal_iron_fortified",
        quantity=grams,
        unit="g",
    )


def gap_report(nutrient: str, confidence: str, req: MealPlanRequest) -> NutrientGapReport:
    targets = general_targets(req)
    target = {"protein": targets.protein.protein_g, "iron": targets.iron.iron_mg}[nutrient]
    return NutrientGapReport(
        status="ok",
        confidence=confidence,  # type: ignore[arg-type]
        directional=confidence == "low",
        days_logged=3 if confidence == "medium" else 8,
        window_days=3 if confidence == "medium" else 7,
        partial_days=0,
        as_of=DAY,
        gaps=[
            NutrientGap(
                nutrient=nutrient,  # type: ignore[arg-type]
                label=nutrient.capitalize(),
                unit="g" if nutrient == "protein" else "mg",
                average=round(target * 0.5, 1),
                target=target,
                ratio=0.5,
                flag="below",
                target_source="DRI",
                target_band="test",
            )
        ],
        targets=targets,
    )


class TestChangeTwoRegression:
    """meal-plan-generation spec: no log inputs -> the Day 4 plan, byte for byte.

    One surgical fixture correction (2026-09-01, day-9-age-diet-aware-targets): the infant
    iron target is 0.27 mg as published, not the 0.3 the old code rounded it to, so the
    three 0-6 month cases' ``targets.iron.iron_mg`` and derived ``coverage.iron`` were
    hand-edited -- six values, verified against a regenerated diff showing items, servings
    and messages byte-identical. The fixture was NOT regenerated.
    """

    @pytest.mark.parametrize("case", json.loads(FIXTURE.read_text(encoding="utf-8")))
    async def test_existing_fixture_unchanged_without_log_inputs(self, case) -> None:
        result = await generate_meal_plan(MealPlanRequest.model_validate(case["request"]), None)
        dumped = result.model_dump(mode="json")
        assert dumped["adjustments"] == [] and dumped["already_logged"] is None
        # The fixture is deliberately NOT regenerated (day-9 design Decision 8): it is the
        # only byte-for-byte proof the composer's output has not moved. ``targets`` gained
        # the day-9 ``items`` list, so it is compared on the Day 4 keys; regenerating the
        # file to absorb that key would quietly discard the guard.
        targets = {k: v for k, v in dumped.pop("targets").items() if k != "items"}
        assert targets == case["result"]["targets"]
        expected = {k: v for k, v in case["result"].items() if k != "targets"}
        # child-notes-restrictions reshaped the note fields; the fixture keeps the Day 4 shape.
        # Every fixture case has no note, so both shapes must say "nothing happened".
        assert expected.pop("override")["conflict"] is False
        assert expected.pop("note_extraction")["status"] == "not_present"
        assert dumped["note_extraction"]["status"] == "not_present"
        assert dumped["overrides"] == [] and dumped["note_outcomes"] == []
        skipped = NEW_RESULT_FIELDS | {
            "note_extraction",
            "overrides",
            "avoidances",
            "note_outcomes",
        }
        assert {k: v for k, v in dumped.items() if k not in skipped} == expected


class TestGapSteering:
    async def test_medium_protein_gap_changes_selection_not_targets(self) -> None:
        req = request(age_months=24, weight_kg=12.5)
        baseline = await generate_meal_plan(req, None)
        steered = await generate_meal_plan(
            req.model_copy(update={"gaps": gap_report("protein", "medium", req)}), None
        )
        assert steered.outcome == "plan"
        assert steered.targets == baseline.targets
        assert [i.food_id for i in steered.items] != [i.food_id for i in baseline.items]
        assert any("highest protein" in i.reason for i in steered.items)
        [adjustment] = steered.adjustments
        assert adjustment.nutrient == "protein" and adjustment.action == "prioritised"
        assert adjustment.confidence == "medium" and "targets unchanged" in adjustment.detail

    async def test_low_confidence_gap_changes_nothing(self) -> None:
        req = request(age_months=24, weight_kg=12.5)
        baseline = await generate_meal_plan(req, None)
        informed = await generate_meal_plan(
            req.model_copy(update={"gaps": gap_report("iron", "low", req)}), None
        )
        assert informed.adjustments == []
        assert informed.model_dump() == baseline.model_dump()

    async def test_insufficient_report_changes_nothing(self) -> None:
        req = request()
        report = NutrientGapReport(
            status="insufficient_data",
            days_logged=0,
            window_days=0,
            partial_days=2,
            as_of=DAY,
            targets=general_targets(req),
        )
        assert (
            await generate_meal_plan(req.model_copy(update={"gaps": report}), None)
        ).model_dump() == (await generate_meal_plan(req, None)).model_dump()

    @pytest.mark.parametrize(
        ("age", "weight", "height"), [(9, 8.8, None), (24, 12.5, None), (48, 16.0, 102.0)]
    )
    async def test_high_iron_gap_respects_upper_limit_and_targets(
        self, age, weight, height
    ) -> None:
        req = request(age_months=age, weight_kg=weight, height_cm=height)
        result = await generate_meal_plan(
            req.model_copy(update={"gaps": gap_report("iron", "high", req)}), None
        )
        assert result.totals.iron_mg <= IRON_UL_MG
        assert result.targets == general_targets(req)
        assert result.adjustments[0].nutrient == "iron"


class TestLoggedToday:
    async def test_partial_day_composes_toward_the_remainder(self) -> None:
        req = request()  # 9 months, 8.8 kg -> 705 kcal general target
        full = await generate_meal_plan(req, None)
        result = await generate_meal_plan(
            req.model_copy(update={"logged_today": [cereal_today(75)]}),
            None,  # 300 kcal
        )
        assert result.outcome == "plan"
        assert result.already_logged is not None and result.already_logged.calories == 300.0
        assert result.targets == full.targets  # the day's targets are still the reference
        remaining = full.targets.calories.calories - 300
        assert result.totals.calories <= 1.1 * remaining
        assert result.totals.calories < full.totals.calories
        assert result.coverage.calories == round(result.totals.calories / remaining, 2)
        assert "already logged" in result.message
        table = get_food_table()
        for item in result.items:
            assert check_food(table.get(item.food_id), 9, ()) == []

    async def test_targets_met_when_little_remains(self) -> None:
        req = request()
        result = await generate_meal_plan(
            req.model_copy(update={"logged_today": [cereal_today(170)]}),
            None,  # 680 kcal
        )
        assert result.outcome == "targets_met"
        assert result.items == [] and result.totals.calories == 0
        assert result.message == TARGETS_MET_MESSAGE
        assert result.disclaimer == DISCLAIMER
        assert result.already_logged is not None and result.already_logged.calories == 680.0
        assert result.targets.calories.calories == 705

    async def test_override_still_wins_with_intake_subtracted(self) -> None:
        llm = RecordingChatModel(
            responses=[note_reply({"row": 1, "target": CALORIES_650, "avoid": []})]
        )
        result = await generate_meal_plan(
            request(
                age_months=8,
                weight_kg=8.5,
                notes=[doctor("Limit to 650 kcal per day.")],
                logged_today=[cereal_today(75)],
            ),
            llm,
        )
        assert result.overrides[0].conflict is True and result.targets.calories.calories == 650
        assert result.already_logged is not None and result.already_logged.calories == 300.0
        assert result.totals.calories <= 1.1 * 350
        assert result.outcome == "plan"

    async def test_empty_log_list_is_the_unlogged_plan(self) -> None:
        req = request()
        assert (await generate_meal_plan(req.model_copy(update={"logged_today": []}), None)) == (
            await generate_meal_plan(req, None)
        )


class TestAuditLogChangeTwo:
    async def test_plan_records_gaps_entries_and_adjustments(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        req = request(age_months=24, weight_kg=12.5)
        entry = cereal_today(15).model_copy(update={"id": "entry-1"})
        result = await generate_meal_plan(
            req.model_copy(
                update={"gaps": gap_report("protein", "medium", req), "logged_today": [entry]}
            ),
            None,
        )
        [record] = audit_records(caplog)
        assert record["outcome"] == "plan"
        assert record["gaps"] == {
            "status": "ok",
            "confidence": "medium",
            "days_logged": 3,
            "window_days": 3,
            "flags": {"protein": "below"},
        }
        assert record["logged_today"]["entries"] == [
            {
                "id": "entry-1",
                "fed_at": "2026-08-27T08:00:00+00:00",
                "feeding_type": "solid",
                "food_id": "infant_cereal_iron_fortified",
            }
        ]
        assert record["logged_today"]["already_logged"]["calories"] == 60.0
        assert record["adjustments"] == [a.model_dump(mode="json") for a in result.adjustments]
        assert record["adjustments"][0]["nutrient"] == "protein"

    async def test_targets_met_is_audited(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await generate_meal_plan(
            request().model_copy(update={"logged_today": [cereal_today(170)]}), None
        )
        [record] = audit_records(caplog)
        assert record["outcome"] == "targets_met" and record["items"] == []
        assert record["logged_today"]["already_logged"]["calories"] == 680.0
        assert record["gaps"] is None and record["adjustments"] == []

    async def test_no_safe_plan_carries_the_new_keys_as_empty(self, caplog, tmp_path) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        table = load_food_table(
            write_table(tmp_path, {**VALID_ENTRY, "id": "grapes", "choking_hazard": True})
        )
        await generate_meal_plan(request(age_months=24, weight_kg=12), None, table)
        [record] = audit_records(caplog)
        assert record["outcome"] == "no_safe_plan"
        assert record["gaps"] is None and record["logged_today"] is None
        assert record["adjustments"] == []


class TestNoteAvoidances:
    """child-notes-restrictions: foods a row names are left out, deterministically, and
    every row gets an outcome."""

    def llm(self, *rows: dict) -> RecordingChatModel:
        return RecordingChatModel(responses=[note_reply(*rows)], calls=[])

    async def test_named_food_is_left_out_with_the_row_as_reason(self) -> None:
        text = "no iron fortified oat cereal"
        result = await generate_meal_plan(
            request(notes=[doctor(text)]),
            self.llm({"row": 1, "target": None, "avoid": ["iron fortified oat cereal"]}),
        )
        assert result.outcome == "plan"
        assert "infant_cereal_iron_fortified" not in {i.food_id for i in result.items}
        excluded = {e.food_id: e.reasons for e in result.exclusions}
        assert excluded["infant_cereal_iron_fortified"] == [
            chat_copy.note_exclusion_reason(NoteKind.DOCTOR, text)
        ]
        [avoidance] = result.avoidances
        assert avoidance.applied and avoidance.food_ids == ["infant_cereal_iron_fortified"]
        [outcome] = result.note_outcomes
        assert outcome.applied is True and outcome.kind is NoteKind.DOCTOR
        assert result.overrides == []

    async def test_food_group_is_left_out_but_the_milk_feed_stays(self) -> None:
        result = await generate_meal_plan(
            request(age_months=8, weight_kg=8.5, notes=[preference("avoid dairy")]),
            self.llm({"row": 1, "target": None, "avoid": ["dairy"]}),
        )
        assert result.outcome == "plan"
        assert FoodCategory.DAIRY not in categories_of(result)
        assert FoodCategory.MILK_FEED in categories_of(result)
        [avoidance] = result.avoidances
        assert avoidance.category == "dairy" and "plain_whole_yogurt" in avoidance.food_ids
        reasons = {e.food_id: e.reasons for e in result.exclusions}
        assert reasons["plain_whole_yogurt"] == [
            chat_copy.note_exclusion_reason(NoteKind.PREFERENCE, "avoid dairy")
        ]

    async def test_ambiguous_phrase_excludes_every_candidate(self) -> None:
        result = await generate_meal_plan(
            request(notes=[preference("no apple")]),
            self.llm({"row": 1, "target": None, "avoid": ["apple"]}),
        )
        [avoidance] = result.avoidances
        assert set(avoidance.food_ids) == {
            "apple_cooked",
            "raw_apple_chunks",
            "unpasteurized_juice",
        }
        assert set(avoidance.food_ids) <= {e.food_id for e in result.exclusions}
        assert not set(avoidance.food_ids) & {i.food_id for i in result.items}

    async def test_unknown_phrase_is_not_applied_and_the_plan_still_comes(self) -> None:
        result = await generate_meal_plan(
            request(notes=[preference("no kale chips")]),
            self.llm({"row": 1, "target": None, "avoid": ["kale chips"]}),
        )
        assert result.outcome == "plan"
        [outcome] = result.note_outcomes
        assert outcome.applied is False
        assert outcome.detail == chat_copy.note_no_match("kale chips")

    async def test_milk_feeds_cannot_be_avoided_by_a_note(self) -> None:
        result = await generate_meal_plan(
            request(notes=[preference("no breast milk")]),
            self.llm({"row": 1, "target": None, "avoid": ["breast milk"]}),
        )
        assert FoodCategory.MILK_FEED in categories_of(result)
        [outcome] = result.note_outcomes
        assert outcome.applied is False and outcome.detail == chat_copy.NOTE_MILK_FEED

    async def test_no_milk_leaves_dairy_out_but_keeps_the_milk_feed_and_says_so(self) -> None:
        result = await generate_meal_plan(
            request(notes=[preference("no milk")]),
            self.llm({"row": 1, "target": None, "avoid": ["milk"]}),
        )
        assert FoodCategory.MILK_FEED in categories_of(result)
        assert "whole_cows_milk" in {e.food_id for e in result.exclusions}
        [outcome] = result.note_outcomes
        assert outcome.applied is True and chat_copy.NOTE_MILK_FEED in outcome.detail

    async def test_doctor_target_and_preference_avoidance_compose(self) -> None:
        result = await generate_meal_plan(
            request(
                age_months=8,
                weight_kg=8.5,
                notes=[doctor("Limit to 650 kcal."), preference("no pork")],
            ),
            self.llm(
                {"row": 1, "target": CALORIES_650, "avoid": []},
                {"row": 2, "target": None, "avoid": ["pork"]},
            ),
        )
        assert result.targets.calories.calories == 650
        assert [o.applied for o in result.note_outcomes] == [True, True]
        assert "pork_tenderloin_cooked" in {e.food_id for e in result.exclusions}

    async def test_no_model_leaves_every_row_not_applied(self) -> None:
        result = await plan(notes=[doctor("no honey"), preference("no pork")])
        assert result.outcome == "plan"
        assert [o.applied for o in result.note_outcomes] == [False, False]
        assert result.avoidances == []

    async def test_audit_records_avoidances_and_outcomes(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await generate_meal_plan(
            request(notes=[preference("no pork")]),
            self.llm({"row": 1, "target": None, "avoid": ["pork"]}),
        )
        [record] = audit_records(caplog)
        assert record["input"]["notes"] == [{"kind": "preference", "text": "no pork"}]
        assert record["avoidances"][0]["food_ids"] == ["pork_tenderloin_cooked"]
        assert record["note_outcomes"][0]["applied"] is True
        assert "note_avoidances" in record["rules"]


class TestInactiveFoods:
    async def test_an_inactive_food_is_never_planned(self) -> None:
        """food-table-admin: the planner composes from active entries only."""
        from backend.nutrition.foods import table_from_revision

        base = get_food_table()
        payload = {
            "source": base.table.source,
            "foods": [
                {**f.model_dump(mode="json"), "is_active": f.id != "infant_cereal_iron_fortified"}
                for f in base.all_foods
            ],
        }
        table = table_from_revision(2, payload)
        result = await generate_meal_plan(request(), None, table)
        assert result.outcome == "plan"
        assert "infant_cereal_iron_fortified" not in {i.food_id for i in result.items}
        assert result.food_table_version == "db-2"
