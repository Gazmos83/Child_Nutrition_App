"""Tool input validation rejects bad input before any calculation (task 1.1; hard rule 7)."""

import pytest
from pydantic import ValidationError

from backend.models.enums import Sex
from backend.schemas.tools import (
    BmiInput,
    CalorieTargetInput,
    DoctorsNoteOverride,
    MealItem,
    MealPlanRequest,
    ProteinTargetInput,
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
