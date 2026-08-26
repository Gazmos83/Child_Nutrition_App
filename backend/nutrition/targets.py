"""Nutrient-target formulas from the Dietary Reference Intakes (design.md Decisions 3-5).

Everything here is arithmetic over the figures in
``knowledge-base/nih-dri-energy-and-protein.md`` and ``nih-dri-micronutrients.md``; a
number quoted in an answer and a number used in a meal plan trace to the same source.
No model call, no database, no I/O: the same input always gives the same output.

Age bands are inclusive in completed months as the source tables write them. "1-3 years"
starts at 13 months, matching the energy table's explicit "13-35 months" (Decision 3).
"""

from backend.models.enums import Sex
from backend.schemas.tools import (
    ActivityLevel,
    BmiInput,
    BmiResult,
    CalorieTargetInput,
    CalorieTargetResult,
    IronTargetResult,
    ProteinTargetInput,
    ProteinTargetResult,
)

DRI_ENERGY_PROTEIN_SOURCE = (
    "Institute of Medicine, Dietary Reference Intakes for Energy, Carbohydrate, Fiber, Fat, "
    "Fatty Acids, Cholesterol, Protein, and Amino Acids (2005), via NIH ODS tables"
)
DRI_MICRONUTRIENT_SOURCE = (
    "Institute of Medicine, Dietary Reference Intakes: Elements (iron, 2001), via NIH ODS tables"
)
BMI_SOURCE = "CDC: BMI = weight (kg) / height (m)^2"

# -- Energy ---------------------------------------------------------------------------------

# (upper age bound inclusive, band label, growth-deposition constant kcal/day)
_INFANT_TODDLER_ENERGY_BANDS: tuple[tuple[int, str, int], ...] = (
    (3, "0–3 months", 175),
    (6, "4–6 months", 56),
    (12, "7–12 months", 22),
    (35, "13–35 months", 20),
)
_CHILD_ENERGY_BAND = "3–8 years"

# Physical-activity coefficients of the 3-8 years EER equations, by sex.
PA_COEFFICIENTS: dict[Sex, dict[ActivityLevel, float]] = {
    Sex.MALE: {
        ActivityLevel.SEDENTARY: 1.00,
        ActivityLevel.LOW_ACTIVE: 1.13,
        ActivityLevel.ACTIVE: 1.26,
        ActivityLevel.VERY_ACTIVE: 1.42,
    },
    Sex.FEMALE: {
        ActivityLevel.SEDENTARY: 1.00,
        ActivityLevel.LOW_ACTIVE: 1.16,
        ActivityLevel.ACTIVE: 1.31,
        ActivityLevel.VERY_ACTIVE: 1.56,
    },
}


def energy_band(age_months: int) -> str:
    for upper, label, _ in _INFANT_TODDLER_ENERGY_BANDS:
        if age_months <= upper:
            return label
    return _CHILD_ENERGY_BAND


def calculate_calorie_target(params: CalorieTargetInput) -> CalorieTargetResult:
    """Estimated Energy Requirement (kcal/day) from the 2005 DRI equations."""
    age, weight = params.age_months, params.weight_kg
    for upper, label, growth in _INFANT_TODDLER_ENERGY_BANDS:
        if age <= upper:
            eer = (89 * weight - 100) + growth
            return CalorieTargetResult(
                calories=max(0, round(eer)),
                band=label,
                formula=f"EER = (89 × {weight:g} kg − 100) + {growth}",
                source=DRI_ENERGY_PROTEIN_SOURCE,
            )

    # 36-60 months: the 3-8 years equation. Validation guarantees height is present.
    assert params.height_cm is not None
    height_m = params.height_cm / 100
    years = age / 12
    pa = PA_COEFFICIENTS[params.sex][params.activity_level]
    if params.sex is Sex.MALE:
        eer = 88.5 - 61.9 * years + pa * (26.7 * weight + 903 * height_m) + 20
        formula = (
            f"EER = 88.5 − 61.9 × {years:.2f} y + {pa} × (26.7 × {weight:g} kg + "
            f"903 × {height_m:.2f} m) + 20"
        )
    else:
        eer = 135.3 - 30.8 * years + pa * (10.0 * weight + 934 * height_m) + 20
        formula = (
            f"EER = 135.3 − 30.8 × {years:.2f} y + {pa} × (10.0 × {weight:g} kg + "
            f"934 × {height_m:.2f} m) + 20"
        )
    return CalorieTargetResult(
        calories=max(0, round(eer)),
        band=_CHILD_ENERGY_BAND,
        formula=formula,
        activity_level=params.activity_level,
        source=DRI_ENERGY_PROTEIN_SOURCE,
    )


# -- Protein --------------------------------------------------------------------------------

# (upper age bound inclusive, band label, g per kg, reference type)
_PROTEIN_BANDS: tuple[tuple[int, str, float, str], ...] = (
    (6, "0–6 months", 1.52, "AI"),
    (12, "7–12 months", 1.2, "RDA"),
    (47, "1–3 years", 1.05, "RDA"),
    (60, "4–8 years", 0.95, "RDA"),
)


def protein_band(age_months: int) -> str:
    return _lookup(_PROTEIN_BANDS, age_months)[1]


def calculate_protein_target(params: ProteinTargetInput) -> ProteinTargetResult:
    _, label, per_kg, ref = _lookup(_PROTEIN_BANDS, params.age_months)
    return ProteinTargetResult(
        protein_g=round(params.weight_kg * per_kg, 1),
        grams_per_kg=per_kg,
        reference_type=ref,  # type: ignore[arg-type]
        band=label,
        source=DRI_ENERGY_PROTEIN_SOURCE,
    )


# -- Iron -----------------------------------------------------------------------------------

# (upper age bound inclusive, band label, mg/day, reference type)
_IRON_BANDS: tuple[tuple[int, str, float, str], ...] = (
    (6, "0–6 months", 0.27, "AI"),
    (12, "7–12 months", 11.0, "RDA"),
    (47, "1–3 years", 7.0, "RDA"),
    (60, "4–8 years", 10.0, "RDA"),
)


def iron_band(age_months: int) -> str:
    return _lookup(_IRON_BANDS, age_months)[1]


def iron_target(age_months: int) -> IronTargetResult:
    _, label, mg, ref = _lookup(_IRON_BANDS, age_months)
    return IronTargetResult(
        iron_mg=round(mg, 1),
        reference_type=ref,  # type: ignore[arg-type]
        band=label,
        source=DRI_MICRONUTRIENT_SOURCE,
    )


# -- BMI ------------------------------------------------------------------------------------


def calculate_bmi(params: BmiInput) -> BmiResult:
    height_m = params.height_cm / 100
    return BmiResult(
        bmi=round(params.weight_kg / (height_m**2), 2),
        weight_kg=params.weight_kg,
        height_cm=params.height_cm,
        source=BMI_SOURCE,
        note=(
            "For children, BMI is interpreted as an age- and sex-specific percentile on a "
            "growth chart, which this tool does not compute."
        ),
    )


# -- helpers --------------------------------------------------------------------------------


def _lookup(bands: tuple[tuple, ...], age_months: int) -> tuple:
    for band in bands:
        if age_months <= band[0]:
            return band
    raise ValueError(f"age_months {age_months} outside supported bands")  # unreachable: validated
