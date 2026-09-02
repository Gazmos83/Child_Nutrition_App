"""Input and output models for the deterministic nutrient tools (Day 4).

Every tool validates its input here before any arithmetic runs (hard rule 7). Ages are in
months only (hard rule 1); allergies and diet preference reuse the Day 1 controlled
vocabularies (hard rule 2). Outputs carry the source and age band behind every number so
Day 5 can display provenance and Day 6 can audit it.

Design.md Decision 12: inputs are floats with sanity bounds, outputs are rounded to display
precision (kcal whole, g/mg one decimal, BMI two).
"""

import datetime as dt
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from backend.models.enums import ActivityLevel, Allergen, DietPreference, FeedingType, Sex
from backend.nutrition.nutrients import REGISTRY, NutrientKey, NutrientUnit, ReferenceType

MIN_AGE_MONTHS = 0
MAX_AGE_MONTHS = 60

# Below this age the DRI energy equation is weight-only; from here it needs height and a
# physical-activity coefficient (design.md Decision 4).
HEIGHT_REQUIRED_FROM_MONTHS = 36

# Sanity limits, not medical ones: they reject typos (a weight in grams, a height in mm),
# not real children.
MAX_WEIGHT_KG = 60.0
MAX_HEIGHT_CM = 150.0


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
        description=(
            "BMI alone is not interpretable for a child; `assess_growth` supplies the "
            "age- and sex-specific percentile."
        )
    )


# -- Growth assessment (growth-assessment spec) ----------------------------------------------

GrowthBand = Literal["well_below", "below", "expected", "above", "well_above"]

# Mirrors backend.nutrition.growth.GrowthIndicator; a Literal here keeps this module from
# importing the computation module it feeds (the layering nutrients.py already follows),
# and a registry-style invariant test asserts the two vocabularies agree.
GrowthIndicatorKey = Literal[
    "weight_for_age",
    "length_height_for_age",
    "weight_for_length_height",
    "bmi_for_age",
]


class GrowthAssessmentInput(_Strict):
    """Height is optional on purpose: the assessment computes what it can and reports the
    rest as skipped, so a parent who knows only the weight still gets weight-for-age."""

    age_months: int = _AGE
    sex: Sex
    weight_kg: float = _WEIGHT
    height_cm: float | None = Field(
        default=None,
        gt=0,
        le=MAX_HEIGHT_CM,
        description=(
            "Length/height in centimetres; optional. Read as recumbent length under "
            "24 months and standing height from 24 months."
        ),
    )


class LmsReference(_Frozen):
    """WHO's −2 SD, median, and +2 SD for the child's sex and age, in the measurement's unit."""

    sd2neg: float
    median: float
    sd2pos: float


class GrowthIndicatorResult(_Frozen):
    indicator: GrowthIndicatorKey
    measurement: float = Field(description="The value placed on the standard.")
    unit: str
    z_score: float = Field(description="WHO LMS z-score, two decimals.")
    percentile: float = Field(ge=0, le=100, description="One decimal.")
    band: GrowthBand = Field(description="WHO cut-offs at −3, −2, +2, +3 SD.")
    who_label: str | None = Field(
        default=None,
        description="WHO's own classification term, only where WHO publishes one.",
    )
    reference: LmsReference


class SkippedIndicator(_Frozen):
    indicator: GrowthIndicatorKey
    reason: str = Field(description="Parent-facing; names the missing or out-of-range input.")


class GrowthAssessmentResult(_Frozen):
    age_months: int
    sex: Sex
    weight_kg: float
    height_cm: float | None
    indicators: list[GrowthIndicatorResult]
    skipped: list[SkippedIndicator]
    source: str = Field(description="Names the standard and its year (hard rule 5).")
    source_url: str
    note: str = Field(
        description="States the completed-month granularity and the length/height reading."
    )


# -- Growth reference curves (growth-charts change) ------------------------------------------

CurveXUnit = Literal["months", "cm"]
CurveTable = Literal["length", "height"]


class GrowthCurve(_Frozen):
    percentile: int = Field(ge=1, le=99)
    values: list[float] = Field(description="One value per x in the set's ``xs``.")


class GrowthCurveSet(_Frozen):
    """One indicator's percentile curves for one sex, sampled over shared x-values."""

    indicator: GrowthIndicatorKey
    x_unit: CurveXUnit
    x_label_table: CurveTable | None = Field(
        default=None, description="Which WHO table a centimetre axis shows; None for age axes."
    )
    y_unit: str
    xs: list[float]
    curves: list[GrowthCurve]

    @model_validator(mode="after")
    def _values_align_with_xs(self) -> GrowthCurveSet:
        for curve in self.curves:
            if len(curve.values) != len(self.xs):
                raise ValueError(
                    f"{self.indicator} P{curve.percentile}: {len(curve.values)} values for "
                    f"{len(self.xs)} x-values"
                )
        return self


class GrowthCurvesResponse(_Frozen):
    sex: Sex
    age_months: int
    indicators: list[GrowthCurveSet]
    source: str = Field(description="Names the standard and its year (hard rule 5).")
    source_url: str


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
    iron_mg: float = Field(ge=0, description="mg/day, as published in the DRI table.")
    reference_type: Literal["AI", "RDA"]
    band: str
    source: str


# Defined here rather than beside the gap report because a target row carries its flag.
GapFlag = Literal["below", "adequate", "above"]


class NutrientTarget(_Frozen):
    """One daily target: the number (or advisory), its provenance, and how it may be used.

    The invariants are enforced, not documented: a row that is not tracked can never carry
    intake or a flag, so an unobservable nutrient reading as a deficit is a validation
    error at the boundary rather than a bug on a parent's screen.
    """

    nutrient: NutrientKey
    label: str
    unit: NutrientUnit
    amount: float | None = Field(
        default=None, ge=0, description="None only for an advisory, which carries text instead."
    )
    reference_type: ReferenceType | None = None
    band: str = ""
    source: str = Field(description="Citation including publication date (hard rule 5).")
    upper_limit: float | None = Field(
        default=None, gt=0, description="Tolerable upper intake level, where published."
    )
    tracked: bool = Field(description="Whether logged intake is compared with this target.")
    derivation: str = Field(
        default="", description="How the number was produced, for the tool-activity display."
    )
    per_kg: float | None = Field(default=None, description="Set for per-kg-of-bodyweight targets.")
    activity_level: ActivityLevel | None = None
    advisory: str | None = None
    advisory_source_date: str | None = None
    display_note: str = ""
    not_tracked_reason: str | None = None
    intake_average: float | None = Field(default=None, ge=0)
    ratio: float | None = None
    flag: GapFlag | None = None

    @model_validator(mode="after")
    def _amount_or_advisory(self) -> NutrientTarget:
        if (self.amount is None) == (self.advisory is None):
            raise ValueError("a target carries exactly one of amount or advisory")
        if self.advisory is not None and not self.advisory_source_date:
            raise ValueError("an advisory carries its source's publication date (hard rule 5)")
        return self

    @model_validator(mode="after")
    def _tracking_invariants(self) -> NutrientTarget:
        if self.tracked and self.amount is None:
            raise ValueError("a tracked nutrient must have a numeric target")
        if not self.tracked:
            if self.intake_average is not None or self.ratio is not None or self.flag is not None:
                raise ValueError("a nutrient that is not tracked can never carry intake or a flag")
            if self.advisory is None and not self.not_tracked_reason:
                raise ValueError("an unscored numeric target carries a parent-facing reason")
        return self


_COMPOSED_NUTRIENTS = ("calories", "protein", "iron")


class NutrientTargets(_Frozen):
    """The child's daily targets, in display priority order. One definition, one shape.

    ``items`` is authoritative. The ``calories``/``protein``/``iron`` computed properties,
    the legacy keyword constructor, and the ``model_copy`` translation exist so that every
    pre-existing consumer -- the composer, the override, gap detection, the frontend --
    keeps compiling and emitting the same JSON (a superset: ``items`` plus the three).
    TODO(day-10): drop the façade once the frontend reads ``items[]`` directly.
    """

    items: tuple[NutrientTarget, ...]

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_shape(cls, data: object) -> object:
        """Synthesize ``items`` from the Day 4 three-field construction or serialization."""
        if not isinstance(data, dict) or "items" in data:
            return data
        legacy = {key: data.get(key) for key in _COMPOSED_NUTRIENTS}
        if any(value is None for value in legacy.values()):
            return data
        rows = []
        for key, value in legacy.items():
            result = (
                _LEGACY_RESULTS[key].model_validate(value) if isinstance(value, dict) else value
            )
            rows.append(_row_from_legacy(key, result))
        return {"items": tuple(rows)}

    @model_validator(mode="after")
    def _well_formed(self) -> NutrientTargets:
        keys = [row.nutrient for row in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("a nutrient appears at most once in a target set")
        missing = [key for key in _COMPOSED_NUTRIENTS if key not in keys]
        if missing:
            raise ValueError(
                f"targets always include the composed-against three; missing {missing}"
            )
        return self

    # -- keyed access -------------------------------------------------------------------

    def get(self, key: NutrientKey) -> NutrientTarget | None:
        return next((row for row in self.items if row.nutrient == key), None)

    def require(self, key: NutrientKey) -> NutrientTarget:
        row = self.get(key)
        if row is None:
            raise KeyError(key)
        return row

    def amount_of(self, key: NutrientKey) -> float:
        amount = self.require(key).amount
        assert amount is not None  # advisories are never composed against or overridden
        return amount

    def tracked(self) -> tuple[NutrientTarget, ...]:
        return tuple(row for row in self.items if row.tracked)

    def with_amount(
        self, key: NutrientKey, value: float, *, source: str, derivation: str = ""
    ) -> NutrientTargets:
        """One nutrient's amount replaced; the doctor's-note override and nothing else."""
        rounded = float(round(value)) if key == "calories" else round(value, 1)
        rows = tuple(
            row.model_copy(update={"amount": rounded, "source": source, "derivation": derivation})
            if row.nutrient == key
            else row
            for row in self.items
        )
        return NutrientTargets(items=rows)

    # -- legacy façade (serialized, so the wire JSON stays a superset of Day 4's) --------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def calories(self) -> CalorieTargetResult:
        row = self.require("calories")
        assert row.amount is not None
        return CalorieTargetResult(
            calories=round(row.amount),
            band=row.band,
            formula=row.derivation,
            activity_level=row.activity_level,
            source=row.source,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def protein(self) -> ProteinTargetResult:
        row = self.require("protein")
        assert row.amount is not None and row.per_kg is not None
        assert row.reference_type in ("AI", "RDA")
        return ProteinTargetResult(
            protein_g=row.amount,
            grams_per_kg=row.per_kg,
            reference_type=row.reference_type,
            band=row.band,
            source=row.source,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def iron(self) -> IronTargetResult:
        row = self.require("iron")
        assert row.amount is not None
        assert row.reference_type in ("AI", "RDA")
        return IronTargetResult(
            iron_mg=row.amount,
            reference_type=row.reference_type,
            band=row.band,
            source=row.source,
        )

    def model_copy(
        self, *, update: dict[str, object] | None = None, deep: bool = False
    ) -> NutrientTargets:
        """Translate legacy ``update={"calories": ...}`` copies into row surgery.

        A computed property silently swallows ``model_copy`` updates, so without this the
        Day 4 call sites would keep the old numbers while appearing to succeed.
        """
        if update and any(key in update for key in _COMPOSED_NUTRIENTS):
            update = dict(update)
            rows = list(self.items)
            for key in _COMPOSED_NUTRIENTS:
                if key not in update:
                    continue
                result = update.pop(key)
                index = next(i for i, row in enumerate(rows) if row.nutrient == key)
                rows[index] = _row_from_legacy(key, result, rows[index])
            update["items"] = tuple(rows)
        return super().model_copy(update=update, deep=deep)


_LEGACY_RESULTS: dict[str, type[_Frozen]] = {
    "calories": CalorieTargetResult,
    "protein": ProteinTargetResult,
    "iron": IronTargetResult,
}

# Display metadata for rows synthesized from the legacy three-field shape, which carries
# none of its own. Matches the registry rows in backend.nutrition.nutrients.
_LEGACY_ROW_DEFAULTS: dict[str, tuple[str, str]] = {
    "calories": ("Calories", "kcal"),
    "protein": ("Protein", "g"),
    "iron": ("Iron", "mg"),
}


def _row_from_legacy(
    key: str, result: object, existing: NutrientTarget | None = None
) -> NutrientTarget:
    update: dict[str, object]
    if isinstance(result, CalorieTargetResult):
        update = {
            "amount": float(result.calories),
            "band": result.band,
            "source": result.source,
            "derivation": result.formula,
            "activity_level": result.activity_level,
            "reference_type": "EER",
        }
    elif isinstance(result, ProteinTargetResult):
        update = {
            "amount": result.protein_g,
            "band": result.band,
            "source": result.source,
            "per_kg": result.grams_per_kg,
            "reference_type": result.reference_type,
        }
    elif isinstance(result, IronTargetResult):
        update = {
            "amount": result.iron_mg,
            "band": result.band,
            "source": result.source,
            "reference_type": result.reference_type,
        }
    else:
        raise TypeError(f"cannot build a {key} target row from {type(result).__name__}")
    if existing is not None:
        return existing.model_copy(update=update)
    label, unit = _LEGACY_ROW_DEFAULTS[key]
    return NutrientTarget(nutrient=key, label=label, unit=unit, tracked=True, **update)  # type: ignore[arg-type]


# -- Food lookup and meal nutrition ---------------------------------------------------------

# Amounts a parent states, shared by the food tools and the feeding log. A sanity ceiling,
# not a medical one: it rejects a quantity typed in the wrong unit.
MAX_FEED_QUANTITY = 2000.0
FeedingUnit = Literal["ml", "g"]

_FOOD_ONLY = Field(
    min_length=1,
    description=(
        "The food only -- its table identifier or its plain name as the parent said it "
        "(e.g. 'sweet potato'), never an amount or a question; resolved in code."
    ),
)
_QUANTITY = Field(
    default=None,
    gt=0,
    le=MAX_FEED_QUANTITY,
    description="Amount the parent named, in `unit` (or the food's own unit when omitted).",
)
_UNIT = Field(default=None, description="Unit of `quantity`: 'g' for solids, 'ml' for liquids.")


class FoodLookupInput(_Strict):
    food_id: str = _FOOD_ONLY
    quantity: float | None = _QUANTITY
    unit: FeedingUnit | None = _UNIT

    @model_validator(mode="after")
    def _unit_needs_quantity(self) -> FoodLookupInput:
        if self.unit is not None and self.quantity is None:
            raise ValueError("unit needs a quantity")
        return self


class MealItem(_Strict):
    """One food in a meal, measured either in table servings or in an amount with unit."""

    food_id: str = _FOOD_ONLY
    servings: float | None = Field(
        default=None, gt=0, le=20, description="Multiples of the food's table serving."
    )
    quantity: float | None = _QUANTITY
    unit: FeedingUnit | None = _UNIT

    @model_validator(mode="after")
    def _exactly_one_measure(self) -> MealItem:
        if (self.servings is None) == (self.quantity is None):
            raise ValueError("give exactly one of servings or quantity")
        if self.unit is not None and self.quantity is None:
            raise ValueError("unit needs a quantity")
        return self


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

# Derived from the registry's overridable rows so the map cannot drift from them; the
# closed ``OverridableNutrient`` literal above is the same set, asserted by test.
UNIT_FOR_NUTRIENT: dict[str, str] = {spec.key: spec.unit for spec in REGISTRY if spec.overridable}


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


# -- Feeding log (Day 5 change 2; feeding-log spec) -----------------------------------------

# Client-held log bounds: the request carries at most this many entries (design Decision 9).
MAX_LOG_ENTRIES = 200
# Sanity limit on one feed, not a nutritional one: rejects a litre typed as millilitres x10.


def _check_timezone(value: str) -> str:
    """An IANA zone name, validated by constructing it (design Decision 4)."""
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError, ValueError, TypeError:
        raise ValueError(f"{value!r} is not a known IANA time zone") from None
    return value


TimeZoneName = Annotated[str, AfterValidator(_check_timezone)]
"""A client-supplied IANA time zone; local calendar days are taken in it."""


class FeedingEntry(_Strict):
    """One thing the child was actually fed.

    Shape rules live here; table facts (does the food exist, is the unit right) are checked
    in ``backend.nutrition.feeding.normalise_entry`` so this model can travel inside a
    request without table I/O. ``quantity`` is optional only for breast milk -- direct
    breastfeeding has no measure, and an invented volume would be a made-up number.
    """

    id: str | None = Field(default=None, min_length=1, max_length=64)
    fed_at: AwareDatetime
    feeding_type: FeedingType
    food_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Food-table id; required for solids, optional milk-feed override, none for water."
        ),
    )
    quantity: float | None = Field(default=None, gt=0, le=MAX_FEED_QUANTITY)
    unit: FeedingUnit = "ml"

    @model_validator(mode="after")
    def _shape_rules(self) -> FeedingEntry:
        kind = self.feeding_type
        if self.quantity is None and kind is not FeedingType.BREASTMILK:
            raise ValueError(f"quantity is required for a {kind.value} feed")
        if kind is FeedingType.SOLID and self.food_id is None:
            raise ValueError("food_id is required for a solid feed")
        if kind is FeedingType.WATER and self.food_id is not None:
            raise ValueError("water has no food_id")
        if kind is not FeedingType.SOLID and self.unit != "ml":
            raise ValueError(f"{kind.value} is measured in ml, not {self.unit}")
        return self


class LoggedFeeding(_Frozen):
    """A feeding entry as the system hands it back: normalised, identified, and priced."""

    entry: FeedingEntry
    food_id: str | None = Field(description="The table food the entry resolved to, if any.")
    food_name: str | None = None
    quantified: bool = Field(description="False for an unmeasured breastfeed.")
    nutrients: NutrientTotals
    source: str


class DailyNutritionInput(_Strict):
    entries: list[FeedingEntry] = Field(default_factory=list, max_length=MAX_LOG_ENTRIES)
    timezone: TimeZoneName = "UTC"
    date: dt.date | None = Field(default=None, description="Local day; defaults to today.")


class DailyNutritionResult(_Frozen):
    date: dt.date
    timezone: str
    entries: list[LoggedFeeding]
    totals: NutrientTotals
    complete: bool = Field(description="At least one entry and no unmeasured feed.")
    unquantified: int = Field(ge=0)
    source: str


class _ChildForTargets(_Strict):
    """The child fields target resolution needs.

    Diet selects which targets are displayed and their order; it never changes a number
    (day-9 design Decision 5 -- there is no vegan RDA, and the registry cannot express one).
    """

    age_months: int = _AGE
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    diet_preference: DietPreference = DietPreference.default()
    doctors_note: str | None = Field(default=None, max_length=4000)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> _ChildForTargets:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        if self.doctors_note is not None and not self.doctors_note.strip():
            object.__setattr__(self, "doctors_note", None)
        return self


class RemainingTargetsInput(_ChildForTargets):
    entries: list[FeedingEntry] = Field(default_factory=list, max_length=MAX_LOG_ENTRIES)
    timezone: TimeZoneName = "UTC"
    date: dt.date | None = Field(default=None, description="Local day; defaults to today.")


class RemainingNutrients(_Frozen):
    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    iron_mg: float = Field(ge=0)


class RemainingTargetsResult(_Frozen):
    date: dt.date
    timezone: str
    targets: NutrientTargets
    intake: NutrientTotals
    remaining: RemainingNutrients = Field(description="targets minus intake, floored at zero.")
    note_extraction: NoteExtraction
    override: OverrideOutcome
    source: str


# -- Nutrient-gap detection (nutrient-gap-detection spec) ----------------------------------

# The registry's trackable keys: every nutrient that can appear in a gap report. The
# composer still emits adjustments only for protein and iron (design Decision 7).
GapNutrient = Literal["calories", "protein", "iron", "calcium"]
GapConfidence = Literal["low", "medium", "high"]


class GapDetectionRequest(_ChildForTargets):
    entries: list[FeedingEntry] = Field(default_factory=list, max_length=MAX_LOG_ENTRIES)
    timezone: TimeZoneName = "UTC"
    as_of: dt.date | None = Field(
        default=None, description="Reference day (excluded from the window); defaults to today."
    )


class NutrientGap(_Frozen):
    nutrient: GapNutrient
    label: str = Field(description="Parent-facing name from the registry (design Decision 10).")
    unit: NutrientUnit
    average: float = Field(ge=0, description="Window average per day, one decimal.")
    target: float = Field(gt=0)
    ratio: float = Field(ge=0, description="average / target, two decimals.")
    flag: GapFlag
    target_source: str
    target_band: str


class NutrientGapReport(_Frozen):
    status: Literal["ok", "insufficient_data"]
    confidence: GapConfidence | None = Field(default=None, description="None when insufficient.")
    directional: bool = Field(
        default=False, description="True at low confidence: flags show direction only."
    )
    days_logged: int = Field(ge=0, description="Complete days in the look-back.")
    window_days: int = Field(ge=0)
    partial_days: int = Field(ge=0, description="Days excluded for an unmeasured feed.")
    as_of: dt.date
    gaps: list[NutrientGap] = Field(default_factory=list)
    targets: NutrientTargets
    note_extraction: NoteExtraction | None = None
    override: OverrideOutcome | None = None


class Adjustment(_Frozen):
    """One change a plan made because of the log (meal-plan-generation spec)."""

    nutrient: GapNutrient
    action: str
    confidence: GapConfidence | None = None
    window_days: int | None = Field(default=None, ge=0, description="Days the gap rests on.")
    detail: str


class FoodSummary(_Frozen):
    """What a food picker needs; no nutrients, no user data (feeding-log spec)."""

    id: str
    name: str
    category: str
    serving_size: float
    serving_unit: str
    min_age_months: int


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
    # Change 2 (feeding log): both optional; with neither, the plan is byte-identical to
    # the Day 4 planner (meal-plan-generation spec, "No log inputs, unchanged output").
    gaps: NutrientGapReport | None = Field(
        default=None, description="A gap report to steer composition; never raises a target."
    )
    logged_today: list[FeedingEntry] = Field(
        default_factory=list,
        max_length=MAX_LOG_ENTRIES,
        description="Today's feeds; their nutrients are subtracted so the plan covers the rest.",
    )
    timezone: TimeZoneName = "UTC"

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


MealPlanOutcome = Literal["plan", "no_safe_plan", "targets_met"]


class MealPlanResult(_Frozen):
    outcome: MealPlanOutcome
    items: list[PlannedItem]
    totals: NutrientTotals
    targets: NutrientTargets = Field(description="Full-day targets, note applied.")
    coverage: NutrientCoverage = Field(
        description="Against what the plan set out to cover: the day, or what remained of it."
    )
    note_extraction: NoteExtraction
    override: OverrideOutcome
    exclusions: list[Exclusion]
    message: str = Field(description="Plain-language summary, or why no safe plan exists.")
    disclaimer: str
    food_table_version: str
    adjustments: list[Adjustment] = Field(
        default_factory=list, description="What the feeding log changed about composition."
    )
    already_logged: NutrientTotals | None = Field(
        default=None, description="Today's logged intake, when entries were supplied."
    )
