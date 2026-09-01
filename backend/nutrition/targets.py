"""Tool-facing nutrient-target functions over the registry's reference figures.

The figures themselves -- the band tables, the energy equation, the source citations --
live in ``backend.nutrition.nutrients``, which is their single home. This module owns the
tool-facing result shapes and BMI, and re-exports the sources so existing callers keep
importing them from here.

No model call, no database, no I/O: the same input always gives the same output.

Age bands are inclusive in completed months as the source tables write them. "1-3 years"
starts at 13 months, matching the energy table's explicit "13-35 months" (Decision 3).
"""

from backend.nutrition.nutrients import (
    DRI_ENERGY_PROTEIN_SOURCE,
    DRI_MICRONUTRIENT_SOURCE,
    IRON_BANDS,
    PROTEIN_BANDS,
    TargetInputs,
    band_for,
    compute_energy,
    energy_band_label,
)
from backend.schemas.tools import (
    BmiInput,
    BmiResult,
    CalorieTargetInput,
    CalorieTargetResult,
    IronTargetResult,
    ProteinTargetInput,
    ProteinTargetResult,
)

__all__ = [
    "BMI_SOURCE",
    "DRI_ENERGY_PROTEIN_SOURCE",
    "DRI_MICRONUTRIENT_SOURCE",
    "calculate_bmi",
    "calculate_calorie_target",
    "calculate_protein_target",
    "energy_band",
    "iron_band",
    "iron_target",
    "protein_band",
]

BMI_SOURCE = "CDC: BMI = weight (kg) / height (m)^2"

# -- Energy ---------------------------------------------------------------------------------


def energy_band(age_months: int) -> str:
    return energy_band_label(age_months)


def calculate_calorie_target(params: CalorieTargetInput) -> CalorieTargetResult:
    """Estimated Energy Requirement (kcal/day) from the 2005 DRI equations."""
    result = compute_energy(
        TargetInputs(
            age_months=params.age_months,
            weight_kg=params.weight_kg,
            sex=params.sex,
            height_cm=params.height_cm,
            activity_level=params.activity_level,
        )
    )
    return CalorieTargetResult(
        calories=max(0, round(result.amount)),
        band=result.band,
        formula=result.derivation,
        activity_level=result.activity_level,
        source=DRI_ENERGY_PROTEIN_SOURCE,
    )


# -- Protein --------------------------------------------------------------------------------


def protein_band(age_months: int) -> str:
    return band_for(PROTEIN_BANDS, age_months).label


def calculate_protein_target(params: ProteinTargetInput) -> ProteinTargetResult:
    band = band_for(PROTEIN_BANDS, params.age_months)
    return ProteinTargetResult(
        protein_g=round(params.weight_kg * band.value, 1),
        grams_per_kg=band.value,
        reference_type=band.reference_type,
        band=band.label,
        source=DRI_ENERGY_PROTEIN_SOURCE,
    )


# -- Iron -----------------------------------------------------------------------------------


def iron_band(age_months: int) -> str:
    return band_for(IRON_BANDS, age_months).label


def iron_target(age_months: int) -> IronTargetResult:
    band = band_for(IRON_BANDS, age_months)
    return IronTargetResult(
        # As published, never rounded: the 0-6 month AI is 0.27 mg, and rounding a quoted
        # table figure to 0.3 broke agreement with the knowledge base (hard rule 5).
        iron_mg=band.value,
        reference_type=band.reference_type,
        band=band.label,
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
