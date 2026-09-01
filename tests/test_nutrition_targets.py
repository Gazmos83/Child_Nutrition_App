"""DRI target formulas are deterministic and band-correct (task 2.1)."""

import pytest
from pydantic import ValidationError

from backend.models.enums import Sex
from backend.nutrition.targets import (
    DRI_ENERGY_PROTEIN_SOURCE,
    DRI_MICRONUTRIENT_SOURCE,
    calculate_bmi,
    calculate_calorie_target,
    calculate_protein_target,
    energy_band,
    iron_band,
    iron_target,
    protein_band,
)
from backend.schemas.tools import ActivityLevel, BmiInput, CalorieTargetInput, ProteinTargetInput


class TestBmi:
    def test_formula(self) -> None:
        result = calculate_bmi(BmiInput(weight_kg=9.0, height_cm=72.0))
        assert result.bmi == round(9.0 / (0.72**2), 2) == 17.36
        assert result.source

    def test_rounded_to_two_decimals(self) -> None:
        result = calculate_bmi(BmiInput(weight_kg=10.0, height_cm=75.0))
        assert result.bmi == 17.78


class TestEnergyBands:
    @pytest.mark.parametrize(
        ("age", "band"),
        [
            (0, "0–3 months"),
            (3, "0–3 months"),
            (4, "4–6 months"),
            (6, "4–6 months"),
            (7, "7–12 months"),
            (12, "7–12 months"),
            (13, "13–35 months"),
            (35, "13–35 months"),
            (36, "3–8 years"),
            (60, "3–8 years"),
        ],
    )
    def test_band_boundaries(self, age: int, band: str) -> None:
        assert energy_band(age) == band

    def test_twelve_and_thirteen_months_differ(self) -> None:
        twelve = calculate_calorie_target(
            CalorieTargetInput(age_months=12, weight_kg=9.5, sex=Sex.MALE)
        )
        thirteen = calculate_calorie_target(
            CalorieTargetInput(age_months=13, weight_kg=9.5, sex=Sex.MALE)
        )
        assert twelve.band != thirteen.band
        assert twelve.calories == round(89 * 9.5 - 100 + 22)
        assert thirteen.calories == round(89 * 9.5 - 100 + 20)


class TestCalorieTarget:
    def test_infant_equation(self) -> None:
        result = calculate_calorie_target(
            CalorieTargetInput(age_months=6, weight_kg=7.5, sex=Sex.FEMALE)
        )
        assert result.calories == round(89 * 7.5 - 100 + 56) == 624
        assert result.band == "4–6 months"
        assert result.activity_level is None
        assert result.source == DRI_ENERGY_PROTEIN_SOURCE
        assert "89 ×" in result.formula

    def test_infant_and_preschooler_differ(self) -> None:
        infant = calculate_calorie_target(
            CalorieTargetInput(age_months=6, weight_kg=7.5, sex=Sex.MALE)
        )
        child = calculate_calorie_target(
            CalorieTargetInput(age_months=48, weight_kg=16, sex=Sex.MALE, height_cm=102)
        )
        assert infant.calories != child.calories
        assert child.calories > infant.calories
        assert child.band == "3–8 years"
        assert child.activity_level is ActivityLevel.LOW_ACTIVE

    def test_boys_equation_at_four_years(self) -> None:
        result = calculate_calorie_target(
            CalorieTargetInput(
                age_months=48, weight_kg=16, sex=Sex.MALE, height_cm=102, activity_level="sedentary"
            )
        )
        expected = 88.5 - 61.9 * 4 + 1.00 * (26.7 * 16 + 903 * 1.02) + 20
        assert result.calories == round(expected)

    def test_girls_equation_at_four_years(self) -> None:
        result = calculate_calorie_target(
            CalorieTargetInput(
                age_months=48,
                weight_kg=16,
                sex=Sex.FEMALE,
                height_cm=102,
                activity_level="sedentary",
            )
        )
        expected = 135.3 - 30.8 * 4 + 1.00 * (10.0 * 16 + 934 * 1.02) + 20
        assert result.calories == round(expected)

    def test_activity_coefficient_changes_result(self) -> None:
        base = dict(age_months=48, weight_kg=16, sex=Sex.MALE, height_cm=102)
        sedentary = calculate_calorie_target(CalorieTargetInput(**base, activity_level="sedentary"))
        very_active = calculate_calorie_target(
            CalorieTargetInput(**base, activity_level="very_active")
        )
        assert very_active.calories > sedentary.calories

    def test_height_required_from_36_months(self) -> None:
        with pytest.raises(ValidationError, match="height_cm is required"):
            CalorieTargetInput(age_months=36, weight_kg=14, sex=Sex.MALE)

    def test_repeated_calls_identical(self) -> None:
        params = CalorieTargetInput(age_months=20, weight_kg=11.2, sex=Sex.FEMALE)
        assert calculate_calorie_target(params) == calculate_calorie_target(params)


class TestProteinTarget:
    @pytest.mark.parametrize(
        ("age", "band", "per_kg", "ref"),
        [
            (0, "0–6 months", 1.52, "AI"),
            (6, "0–6 months", 1.52, "AI"),
            (8, "7–12 months", 1.2, "RDA"),
            (12, "7–12 months", 1.2, "RDA"),
            (13, "1–3 years", 1.05, "RDA"),
            (47, "1–3 years", 1.05, "RDA"),
            (48, "4–8 years", 0.95, "RDA"),
            (60, "4–8 years", 0.95, "RDA"),
        ],
    )
    def test_bands(self, age: int, band: str, per_kg: float, ref: str) -> None:
        result = calculate_protein_target(ProteinTargetInput(age_months=age, weight_kg=10))
        assert protein_band(age) == band == result.band
        assert result.grams_per_kg == per_kg
        assert result.reference_type == ref
        assert result.protein_g == round(10 * per_kg, 1)
        assert result.source == DRI_ENERGY_PROTEIN_SOURCE

    def test_eight_month_old_uses_7_to_12_month_value(self) -> None:
        result = calculate_protein_target(ProteinTargetInput(age_months=8, weight_kg=8.5))
        assert result.band == "7–12 months"
        assert result.protein_g == 10.2


class TestIronTarget:
    @pytest.mark.parametrize(
        ("age", "band", "mg"),
        [
            (3, "0–6 months", 0.27),
            (8, "7–12 months", 11.0),
            (24, "1–3 years", 7.0),
            (50, "4–8 years", 10.0),
        ],
    )
    def test_bands(self, age: int, band: str, mg: float) -> None:
        result = iron_target(age)
        assert iron_band(age) == band == result.band
        assert result.iron_mg == mg
        assert result.source == DRI_MICRONUTRIENT_SOURCE
