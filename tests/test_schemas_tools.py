"""Tool input validation rejects bad input before any calculation (task 1.1; hard rule 7)."""

from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from backend.models.enums import FeedingType, Sex
from backend.nutrition.growth import GrowthIndicator
from backend.schemas.tools import (
    BmiInput,
    CalorieTargetInput,
    DailyNutritionInput,
    DoctorsNoteOverride,
    FeedingEntry,
    FoodLookupInput,
    GapDetectionRequest,
    GrowthAssessmentInput,
    GrowthIndicatorKey,
    MealItem,
    MealPlanRequest,
    ProteinTargetInput,
    RemainingTargetsInput,
)


class TestAgeAndBodyMeasurements:
    def test_age_above_60_months_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CalorieTargetInput(age_months=72, weight_kg=20, sex=Sex.MALE, height_cm=110)
        with pytest.raises(ValidationError):
            ProteinTargetInput(age_months=72, weight_kg=20)
        with pytest.raises(ValidationError):
            MealPlanRequest(age_months=72, weight_kg=20, sex=Sex.MALE, height_cm=110)

    def test_negative_age_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProteinTargetInput(age_months=-1, weight_kg=5)

    @pytest.mark.parametrize("weight", [0, -3.2])
    def test_non_positive_weight_rejected(self, weight: float) -> None:
        with pytest.raises(ValidationError):
            BmiInput(weight_kg=weight, height_cm=70)
        with pytest.raises(ValidationError):
            CalorieTargetInput(age_months=8, weight_kg=weight, sex=Sex.FEMALE)
        with pytest.raises(ValidationError):
            ProteinTargetInput(age_months=8, weight_kg=weight)
        with pytest.raises(ValidationError):
            MealPlanRequest(age_months=8, weight_kg=weight, sex=Sex.FEMALE)

    @pytest.mark.parametrize("height", [0, -70])
    def test_non_positive_height_rejected(self, height: float) -> None:
        with pytest.raises(ValidationError):
            BmiInput(weight_kg=8, height_cm=height)
        with pytest.raises(ValidationError):
            CalorieTargetInput(age_months=40, weight_kg=15, sex=Sex.MALE, height_cm=height)

    def test_height_required_from_36_months(self) -> None:
        with pytest.raises(ValidationError, match="height_cm is required from 36 months"):
            CalorieTargetInput(age_months=40, weight_kg=15, sex=Sex.MALE)
        with pytest.raises(ValidationError, match="height_cm is required from 36 months"):
            MealPlanRequest(age_months=40, weight_kg=15, sex=Sex.MALE)

    def test_height_optional_below_36_months(self) -> None:
        assert CalorieTargetInput(age_months=35, weight_kg=13, sex=Sex.MALE).height_cm is None
        assert MealPlanRequest(age_months=8, weight_kg=8, sex=Sex.FEMALE).height_cm is None

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProteinTargetInput(age_months=8, weight_kg=8, age_years=1)  # type: ignore[call-arg]


class TestGrowthAssessmentInput:
    """growth-assessment spec: inputs are validated before any lookup (hard rules 1, 2, 7)."""

    def test_valid_input_with_and_without_height(self) -> None:
        with_height = GrowthAssessmentInput(
            age_months=8, sex=Sex.FEMALE, weight_kg=8.5, height_cm=69
        )
        assert with_height.height_cm == 69
        without = GrowthAssessmentInput(age_months=8, sex=Sex.FEMALE, weight_kg=8.5)
        assert without.height_cm is None

    def test_age_above_60_months_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthAssessmentInput(age_months=61, sex=Sex.FEMALE, weight_kg=10)

    def test_zero_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthAssessmentInput(age_months=8, sex=Sex.FEMALE, weight_kg=0)

    def test_height_above_sanity_limit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthAssessmentInput(age_months=8, sex=Sex.FEMALE, weight_kg=8.5, height_cm=151)

    def test_off_vocabulary_sex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthAssessmentInput(age_months=8, sex="other", weight_kg=8.5)  # type: ignore[arg-type]

    def test_indicator_vocabulary_matches_the_enum(self) -> None:
        """The schemas' Literal and the growth module's StrEnum must never drift."""
        assert set(get_args(GrowthIndicatorKey)) == {i.value for i in GrowthIndicator}


class TestControlledVocabularies:
    def test_unknown_allergen_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MealPlanRequest(age_months=8, weight_kg=8, sex=Sex.FEMALE, allergies={"gluten"})

    def test_unknown_diet_preference_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MealPlanRequest(age_months=8, weight_kg=8, sex=Sex.FEMALE, diet_preference="keto")

    def test_unknown_sex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CalorieTargetInput(age_months=8, weight_kg=8, sex="other")

    def test_allergies_accept_enum_values(self) -> None:
        request = MealPlanRequest(
            age_months=8, weight_kg=8, sex=Sex.FEMALE, allergies={"peanut", "milk"}
        )
        assert {a.value for a in request.allergies} == {"peanut", "milk"}


class TestDoctorsNoteOverride:
    def test_valid_override(self) -> None:
        override = DoctorsNoteOverride(nutrient="calories", direction="max", value=650, unit="kcal")
        assert override.value == 650

    def test_unrecognised_nutrient_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DoctorsNoteOverride(nutrient="sodium", direction="max", value=1, unit="mg")

    def test_mismatched_unit_rejected(self) -> None:
        with pytest.raises(ValidationError, match="calories must be expressed in kcal"):
            DoctorsNoteOverride(nutrient="calories", direction="max", value=650, unit="g")

    def test_non_positive_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DoctorsNoteOverride(nutrient="iron", direction="target", value=0, unit="mg")

    def test_unknown_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DoctorsNoteOverride(nutrient="iron", direction="about", value=7, unit="mg")


class TestMealPlanRequestNormalisation:
    def test_blank_note_becomes_none(self) -> None:
        request = MealPlanRequest(age_months=8, weight_kg=8, sex=Sex.FEMALE, doctors_note="   ")
        assert request.doctors_note is None

    def test_meal_item_servings_positive(self) -> None:
        with pytest.raises(ValidationError):
            MealItem(food_id="banana", servings=0)


class TestFeedingEntry:
    """Change 2 task 1.2: shape rules for logged feeds (feeding-log spec)."""

    AT = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)

    def test_breastmilk_accepted_without_quantity(self) -> None:
        entry = FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.BREASTMILK)
        assert entry.quantity is None and entry.food_id is None and entry.unit == "ml"

    def test_formula_without_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError, match="quantity is required for a formula feed"):
            FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.FORMULA)

    def test_solid_without_food_rejected(self) -> None:
        with pytest.raises(ValidationError, match="food_id is required for a solid feed"):
            FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.SOLID, quantity=30, unit="g")

    def test_water_with_food_rejected(self) -> None:
        with pytest.raises(ValidationError, match="water has no food_id"):
            FeedingEntry(
                fed_at=self.AT, feeding_type=FeedingType.WATER, food_id="banana", quantity=50
            )

    @pytest.mark.parametrize("quantity", [0, -10])
    def test_non_positive_quantity_rejected(self, quantity: float) -> None:
        with pytest.raises(ValidationError):
            FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.FORMULA, quantity=quantity)

    def test_unit_outside_ml_or_g_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedingEntry(
                fed_at=self.AT,
                feeding_type=FeedingType.SOLID,
                food_id="banana",
                quantity=1,
                unit="kg",  # type: ignore[arg-type]
            )

    def test_milk_feed_in_grams_rejected(self) -> None:
        with pytest.raises(ValidationError, match="formula is measured in ml"):
            FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.FORMULA, quantity=150, unit="g")

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedingEntry(fed_at=datetime(2026, 8, 27, 9, 30), feeding_type=FeedingType.BREASTMILK)

    def test_off_vocabulary_feeding_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedingEntry(fed_at=self.AT, feeding_type="bottle", quantity=100)  # type: ignore[arg-type]

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.WATER, quantity=50, kcal=3)  # type: ignore[call-arg]


class TestLogInputs:
    AT = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)

    def test_bad_timezone_rejected_everywhere(self) -> None:
        for model in (DailyNutritionInput, RemainingTargetsInput, GapDetectionRequest):
            with pytest.raises(ValidationError, match="Mars/Olympus"):
                model.model_validate(
                    {"age_months": 8, "weight_kg": 8.5, "sex": "female", "timezone": "Mars/Olympus"}
                )

    def test_valid_timezone_and_default(self) -> None:
        assert DailyNutritionInput(timezone="Asia/Tokyo").timezone == "Asia/Tokyo"
        assert DailyNutritionInput().timezone == "UTC"

    def test_log_bounded_to_200_entries(self) -> None:
        entry = FeedingEntry(fed_at=self.AT, feeding_type=FeedingType.BREASTMILK)
        assert len(DailyNutritionInput(entries=[entry] * 200).entries) == 200
        with pytest.raises(ValidationError):
            DailyNutritionInput(entries=[entry] * 201)

    def test_gap_request_needs_height_from_36_months(self) -> None:
        with pytest.raises(ValidationError, match="height_cm is required from 36 months"):
            GapDetectionRequest(age_months=40, weight_kg=15, sex=Sex.MALE)


class TestFoodLookupQuantity:
    """food-lookup-quantities: the amount travels beside the food, never inside its name."""

    def test_quantity_and_unit_are_optional(self) -> None:
        assert FoodLookupInput(food_id="sweet potato").quantity is None
        params = FoodLookupInput(food_id="sweet potato", quantity=20, unit="g")
        assert (params.quantity, params.unit) == (20, "g")
        assert FoodLookupInput(food_id="formula", quantity=150).unit is None

    @pytest.mark.parametrize(
        "body",
        [
            {"food_id": "sweet potato", "quantity": 0, "unit": "g"},
            {"food_id": "sweet potato", "quantity": 20, "unit": "oz"},
            {"food_id": "sweet potato", "unit": "g"},  # unit needs a quantity
            {"food_id": "sweet potato", "quantity": 5000, "unit": "g"},
        ],
    )
    def test_bad_amounts_are_rejected(self, body: dict) -> None:
        with pytest.raises(ValidationError):
            FoodLookupInput.model_validate(body)

    def test_meal_item_takes_exactly_one_measure(self) -> None:
        assert MealItem(food_id="banana", servings=1).quantity is None
        assert MealItem(food_id="banana", quantity=25, unit="g").servings is None
        for body in (
            {"food_id": "banana"},
            {"food_id": "banana", "servings": 1, "quantity": 25},
            {"food_id": "banana", "servings": 1, "unit": "g"},
        ):
            with pytest.raises(ValidationError):
                MealItem.model_validate(body)
