"""Input and output models for the deterministic nutrient tools (Day 4).

Every tool validates its input here before any arithmetic runs (hard rule 7). Ages are in
months only (hard rule 1); allergies and diet preference reuse the Day 1 controlled
vocabularies (hard rule 2). Outputs carry the source and age band behind every number so
Day 5 can display provenance and Day 6 can audit it.

Design.md Decision 12: inputs are floats with sanity bounds, outputs are rounded to display
precision (kcal whole, g/mg one decimal, BMI two).
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import Allergen, DietPreference, Sex

MIN_AGE_MONTHS = 0
MAX_AGE_MONTHS = 60

# Below this age the DRI energy equation is weight-only; from here it needs height and a
# physical-activity coefficient (design.md Decision 4).
HEIGHT_REQUIRED_FROM_MONTHS = 36

# Sanity limits, not medical ones: they reject typos (a weight in grams, a height in mm),
# not real children.
MAX_WEIGHT_KG = 60.0
MAX_HEIGHT_CM = 150.0


class ActivityLevel(StrEnum):
    """Physical-activity categories of the 2005 DRI energy equations."""

    SEDENTARY = "sedentary"
    LOW_ACTIVE = "low_active"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


# -- shared field definitions ---------------------------------------------------------------

_AGE = Field(ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS, description="Child's age in completed months.")
_WEIGHT = Field(gt=0, le=MAX_WEIGHT_KG, description="Weight in kilograms.")
_HEIGHT = Field(gt=0, le=MAX_HEIGHT_CM, description="Height (or recumbent length) in centimetres.")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class _Strict(BaseModel):
    """Inputs: unknown fields are an error, so a misspelt parameter cannot be ignored."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# -- BMI ------------------------------------------------------------------------------------


class BmiInput(_Strict):
    weight_kg: float = _WEIGHT
    height_cm: float = _HEIGHT


class BmiResult(_Frozen):
    bmi: float = Field(description="weight_kg / height_m², rounded to two decimals.")
    weight_kg: float
    height_cm: float
    source: str
    note: str = Field(
        description="BMI alone is not interpretable for a child; a percentile needs a growth chart."
    )


# -- Calorie target -------------------------------------------------------------------------


class CalorieTargetInput(_Strict):
    age_months: int = _AGE
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(
        default=None,
        gt=0,
        le=MAX_HEIGHT_CM,
        description=f"Required from {HEIGHT_REQUIRED_FROM_MONTHS} months (DRI 3–8 y equation).",
    )
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _height_required_for_older_children(self) -> CalorieTargetInput:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        return self


class CalorieTargetResult(_Frozen):
    calories: int = Field(ge=0, description="Estimated Energy Requirement, kcal/day, whole kcal.")
    band: str = Field(description="Age band of the equation used, e.g. '7–12 months'.")
    formula: str = Field(description="The equation applied, for the tool-activity display.")
    activity_level: ActivityLevel | None = Field(
        default=None, description="Only set when the equation used a PA coefficient."
    )
    source: str


# -- Protein target -------------------------------------------------------------------------


class ProteinTargetInput(_Strict):
    age_months: int = _AGE
    weight_kg: float = _WEIGHT


class ProteinTargetResult(_Frozen):
    protein_g: float = Field(ge=0, description="g/day, one decimal.")
    grams_per_kg: float
    reference_type: Literal["AI", "RDA"]
    band: str
    source: str


# -- Iron target ----------------------------------------------------------------------------


class IronTargetResult(_Frozen):
    iron_mg: float = Field(ge=0, description="mg/day, one decimal.")
    reference_type: Literal["AI", "RDA"]
    band: str
    source: str


class NutrientTargets(_Frozen):
    """The three daily targets a meal plan is composed against."""

    calories: CalorieTargetResult
    protein: ProteinTargetResult
    iron: IronTargetResult


# -- Food lookup and meal nutrition ---------------------------------------------------------


class FoodLookupInput(_Strict):
    food_id: str = Field(min_length=1, description="Stable identifier from the food table.")


class MealItem(_Strict):
    food_id: str = Field(min_length=1)
    servings: float = Field(gt=0, le=20, description="Multiples of the food's table serving.")


class MealNutritionInput(_Strict):
    items: list[MealItem] = Field(min_length=1)


class NutrientTotals(_Frozen):
    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    iron_mg: float = Field(ge=0)
    calcium_mg: float = Field(ge=0)


class MealNutritionResult(_Frozen):
    totals: NutrientTotals
    counted: list[MealItem] = Field(description="Items that were found and summed.")
    missing: list[str] = Field(
        default_factory=list,
        description="Food ids not in the table. Reported, never silently dropped.",
    )
    source: str


# -- Doctor's-note override -----------------------------------------------------------------

OverridableNutrient = Literal["calories", "protein", "iron"]
OverrideDirection = Literal["max", "min", "target"]
NutrientUnit = Literal["kcal", "g", "mg"]

UNIT_FOR_NUTRIENT: dict[str, str] = {"calories": "kcal", "protein": "g", "iron": "mg"}


class DoctorsNoteOverride(_Strict):
    """A clinician's numeric instruction, bounded to three nutrients and three directions.

    The nutrient set is closed on purpose: an extraction naming anything else fails
    validation and is reported as unparsed rather than passed through (spec: bounded).
    """

    nutrient: OverridableNutrient
    direction: OverrideDirection
    value: float = Field(gt=0)
    unit: NutrientUnit

    @model_validator(mode="after")
    def _unit_matches_nutrient(self) -> DoctorsNoteOverride:
        expected = UNIT_FOR_NUTRIENT[self.nutrient]
        if self.unit != expected:
            raise ValueError(f"{self.nutrient} must be expressed in {expected}, got {self.unit}")
        return self


NoteExtractionStatus = Literal["not_present", "applied", "no_numeric_target", "unparsed"]


class NoteExtraction(_Frozen):
    status: NoteExtractionStatus
    override: DoctorsNoteOverride | None = None
    detail: str = Field(default="", description="Why, when status is not 'applied'.")


class OverrideOutcome(_Frozen):
    """What deterministic override application decided (hard rule 3)."""

    conflict: bool
    source: Literal["general_target", "doctors_note"]
    nutrient: OverridableNutrient | None = None
    general_value: float | None = None
    applied_value: float | None = None
    detail: str = ""


# -- Meal plan ------------------------------------------------------------------------------


class MealPlanRequest(_Strict):
    age_months: int = _AGE
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    diet_preference: DietPreference = DietPreference.default()
    allergies: frozenset[Allergen] = Field(default_factory=frozenset)
    doctors_note: str | None = Field(default=None, max_length=4000)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> MealPlanRequest:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        if self.doctors_note is not None and not self.doctors_note.strip():
            object.__setattr__(self, "doctors_note", None)
        return self


MealSlot = Literal["breakfast", "lunch", "dinner", "snack", "milk feed"]


class PlannedItem(_Frozen):
    food_id: str
    name: str
    servings: float = Field(gt=0)
    serving_size: float
    serving_unit: str
    meal: MealSlot
    reason: str = Field(description="Why the composer chose it, e.g. 'grain; highest iron'.")


class Exclusion(_Frozen):
    food_id: str
    reasons: list[str] = Field(min_length=1)


class NutrientCoverage(_Frozen):
    calories: float = Field(ge=0, description="totals / target, e.g. 0.95.")
    protein: float = Field(ge=0)
    iron: float = Field(ge=0)


class MealPlanResult(_Frozen):
    outcome: Literal["plan", "no_safe_plan"]
    items: list[PlannedItem]
    totals: NutrientTotals
    targets: NutrientTargets
    coverage: NutrientCoverage
    note_extraction: NoteExtraction
    override: OverrideOutcome
    exclusions: list[Exclusion]
    message: str = Field(description="Plain-language summary, or why no safe plan exists.")
    disclaimer: str
    food_table_version: str
