"""The nutrient registry: one declarative home for every reference intake figure.

Before this module the figures lived in three tuple tables with different shapes, and a
nutrient existed only as a name repeated across the target, gap and override code. A
nutrient is now a row here, so adding one is a table entry rather than an eleven-site diff.

Values are quoted from the knowledge base, so a number shown in a target and a number
cited in a RAG answer trace to the same source (hard rule 5). ``tests`` asserts that
agreement mechanically rather than trusting it.

Age bands are inclusive in completed months, matching how the source tables are written;
see ``backend.nutrition.targets`` for the band-boundary convention.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from backend.models.enums import ActivityLevel, DietPreference, Sex

# A band table row states a published amount, so it is an Adequate Intake or a Recommended
# Dietary Allowance. An Estimated Energy Requirement is never a table row -- it comes from
# an equation -- which is why it is absent here.
BandReferenceType = Literal["AI", "RDA"]
ReferenceType = Literal["AI", "RDA", "EER"]

# The registry owns this vocabulary; ``backend.schemas.tools`` imports it so a unit cannot
# be spelled two ways. Micrograms and international units arrive with B12 and vitamin D.
NutrientUnit = Literal["kcal", "g", "mg", "µg", "IU"]

NutrientKey = Literal[
    "calories",
    "protein",
    "iron",
    "vitamin_d",
    "calcium",
    "vitamin_b12",
    "dha",
]


@dataclass(frozen=True, slots=True)
class Band:
    """One row of a published reference intake table."""

    upper_age_months: int
    """Inclusive upper bound of the band, in completed months."""
    label: str
    """Band label verbatim from the source table, e.g. '7–12 months'."""
    value: float
    """The published amount: a daily total, or per kg of body weight for protein."""
    reference_type: BandReferenceType
    upper_limit: float | None = None
    """Tolerable upper intake level for this band, where one is published."""


def band_for(bands: tuple[Band, ...], age_months: int) -> Band:
    """The band covering ``age_months``.

    Raises ``ValueError`` above the last band; every caller validates age first, so this
    signals a table that does not reach the supported age rather than bad user input.
    """
    for band in bands:
        if age_months <= band.upper_age_months:
            return band
    raise ValueError(f"age_months {age_months} is above the last band ({bands[-1].label})")


# -- derivation styles ----------------------------------------------------------------------
#
# Three shapes, because the nutrients genuinely differ: iron is a flat table value, protein
# is per kg of body weight, and energy is an equation. A closed union keeps ``evaluate``
# exhaustive without an ``Any`` in sight.


@dataclass(frozen=True, slots=True)
class TargetInputs:
    """Everything any derivation is allowed to read about the child."""

    age_months: int
    weight_kg: float
    sex: Sex
    height_cm: float | None
    activity_level: ActivityLevel


@dataclass(frozen=True, slots=True)
class EquationResult:
    amount: float
    band: str
    derivation: str
    """The equation as applied, for the tool-activity display."""
    activity_level: ActivityLevel | None = None
    """Only set when the equation used a physical-activity coefficient."""


@dataclass(frozen=True, slots=True)
class FlatBands:
    """``value`` is the daily amount: iron, calcium, vitamin D, B12."""

    bands: tuple[Band, ...]


@dataclass(frozen=True, slots=True)
class PerKgBands:
    """``value`` is an amount per kg of body weight: protein."""

    bands: tuple[Band, ...]


@dataclass(frozen=True, slots=True)
class Equation:
    """Energy. Deliberately a named function, not table rows.

    The 3–8 year Estimated Energy Requirement is
    ``88.5 − 61.9 × y + PA × (26.7 × kg + 903 × m) + 20``. Expressing that declaratively
    would cost the type safety this union exists for, so the registry records only *that*
    energy is equation-derived and who computes it.
    """

    band_labels: tuple[tuple[int, str], ...]
    compute: Callable[[TargetInputs], EquationResult]


@dataclass(frozen=True, slots=True)
class Advisory:
    """Guidance with no number, e.g. omega-3 DHA for a vegan child."""

    text: str
    source_date: str


Derivation = FlatBands | PerKgBands | Equation | Advisory


# -- the registry row -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NutrientSpec:
    """One nutrient: its reference data, how it may be used, and how it is displayed."""

    key: NutrientKey
    label: str
    unit: NutrientUnit
    """Vestigial for an ``Advisory`` row, which carries no amount. Kept non-optional so
    every other row is guaranteed a unit."""
    derivation: Derivation
    source: str
    """Citation including publication date (hard rule 5)."""

    # -- tracking ---------------------------------------------------------------------------
    intake_field: str | None = None
    """Attribute on ``NutrientTotals``/``FoodItem`` supplying intake. ``None`` means the
    feeding log cannot observe this nutrient at all, so it is never flagged."""
    untrackable_diets: frozenset[DietPreference] = frozenset()
    """Diets for which the food table has no permitted source, so a flag could only ever
    read ``below`` -- which cannot tell a supplemented child from an unsupplemented one."""
    not_tracked_reason: str = ""
    """Parent-facing explanation, required whenever the nutrient is not tracked."""

    # -- doctor's note ----------------------------------------------------------------------
    overridable: bool = False
    """Stays true for exactly calories, protein and iron; see the doctors-note-override spec."""

    # -- display ----------------------------------------------------------------------------
    priority: int = 100
    """Lower sorts first."""
    priority_by_age: tuple[tuple[int, int], ...] = ()
    """(inclusive upper age in months, priority) -- same convention as the bands."""
    priority_by_diet: tuple[tuple[DietPreference, int], ...] = ()
    only_for_diets: frozenset[DietPreference] | None = None
    """``None`` displays for every diet."""
    display_note: str = field(default="")
    """Shown beside the value even when the nutrient is tracked."""
    display_note_by_diet: tuple[tuple[DietPreference, str], ...] = ()
    """Diet-specific note taking precedence over ``display_note``, e.g. B12 supplement
    guidance for a vegan child."""

    def tracked_for(self, diet: DietPreference) -> bool:
        """Whether logged intake is compared against this target for this diet."""
        return self.intake_field is not None and diet not in self.untrackable_diets

    def note_for(self, diet: DietPreference) -> str:
        for preference, note in self.display_note_by_diet:
            if preference is diet:
                return note
        return self.display_note


# -- sources --------------------------------------------------------------------------------

DRI_ENERGY_PROTEIN_SOURCE = (
    "Institute of Medicine, Dietary Reference Intakes for Energy, Carbohydrate, Fiber, Fat, "
    "Fatty Acids, Cholesterol, Protein, and Amino Acids (2005), via NIH ODS tables"
)
DRI_MICRONUTRIENT_SOURCE = (
    "Institute of Medicine, Dietary Reference Intakes: Elements (iron, 2001), via NIH ODS tables"
)
DRI_VITAMIN_MINERAL_SOURCE = (
    "National Academies (Institute of Medicine), Dietary Reference Intake reports 1997–2011, "
    "including the 2011 calcium and vitamin D report, via NIH ODS tables"
)
AAP_VEGETARIAN_SOURCE = (
    "American Academy of Pediatrics, Pediatric Nutrition, 8th ed. (2020), vegetarian and "
    "vegan diets guidance"
)


# -- energy ---------------------------------------------------------------------------------
#
# Energy is the one nutrient whose reference figure is an equation rather than a table
# value, so it lives here as code beside the tables it belongs with. The public tool
# function ``backend.nutrition.targets.calculate_calorie_target`` delegates to it and still
# owns the tool-facing result shape.

# (inclusive upper age in months, band label, growth-deposition constant kcal/day)
ENERGY_BANDS: tuple[tuple[int, str, int], ...] = (
    (3, "0–3 months", 175),
    (6, "4–6 months", 56),
    (12, "7–12 months", 22),
    (35, "13–35 months", 20),
)
CHILD_ENERGY_BAND = "3–8 years"

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


def energy_band_label(age_months: int) -> str:
    for upper, label, _ in ENERGY_BANDS:
        if age_months <= upper:
            return label
    return CHILD_ENERGY_BAND


def compute_energy(inputs: TargetInputs) -> EquationResult:
    """Estimated Energy Requirement, kcal/day, from the 2005 DRI equations."""
    age, weight = inputs.age_months, inputs.weight_kg
    for upper, label, growth in ENERGY_BANDS:
        if age <= upper:
            return EquationResult(
                amount=(89 * weight - 100) + growth,
                band=label,
                derivation=f"EER = (89 × {weight:g} kg − 100) + {growth}",
            )

    # 36-60 months: the 3-8 years equation. Validation guarantees height is present.
    assert inputs.height_cm is not None
    height_m = inputs.height_cm / 100
    years = age / 12
    pa = PA_COEFFICIENTS[inputs.sex][inputs.activity_level]
    if inputs.sex is Sex.MALE:
        eer = 88.5 - 61.9 * years + pa * (26.7 * weight + 903 * height_m) + 20
        derivation = (
            f"EER = 88.5 − 61.9 × {years:.2f} y + {pa} × (26.7 × {weight:g} kg + "
            f"903 × {height_m:.2f} m) + 20"
        )
    else:
        eer = 135.3 - 30.8 * years + pa * (10.0 * weight + 934 * height_m) + 20
        derivation = (
            f"EER = 135.3 − 30.8 × {years:.2f} y + {pa} × (10.0 × {weight:g} kg + "
            f"934 × {height_m:.2f} m) + 20"
        )
    return EquationResult(
        amount=eer,
        band=CHILD_ENERGY_BAND,
        derivation=derivation,
        activity_level=inputs.activity_level,
    )


# -- band tables ----------------------------------------------------------------------------

# Protein is published per kg of body weight, so ``value`` is g/kg, not a daily total.
PROTEIN_BANDS: tuple[Band, ...] = (
    Band(6, "0–6 months", 1.52, "AI"),
    Band(12, "7–12 months", 1.2, "RDA"),
    Band(47, "1–3 years", 1.05, "RDA"),
    Band(60, "4–8 years", 0.95, "RDA"),
)

# Iron is a flat daily amount per band. The UL is 40 mg/day across 0–13 years.
IRON_BANDS: tuple[Band, ...] = (
    Band(6, "0–6 months", 0.27, "AI", 40.0),
    Band(12, "7–12 months", 11.0, "RDA", 40.0),
    Band(47, "1–3 years", 7.0, "RDA", 40.0),
    Band(60, "4–8 years", 10.0, "RDA", 40.0),
)


# -- the registry ---------------------------------------------------------------------------

REGISTRY: tuple[NutrientSpec, ...] = (
    NutrientSpec(
        key="calories",
        label="Calories",
        unit="kcal",
        derivation=Equation(
            band_labels=tuple((upper, label) for upper, label, _ in ENERGY_BANDS)
            + ((60, CHILD_ENERGY_BAND),),
            compute=compute_energy,
        ),
        source=DRI_ENERGY_PROTEIN_SOURCE,
        intake_field="calories",
        overridable=True,
        priority=10,
    ),
    NutrientSpec(
        key="protein",
        label="Protein",
        unit="g",
        derivation=PerKgBands(PROTEIN_BANDS),
        source=DRI_ENERGY_PROTEIN_SOURCE,
        intake_field="protein_g",
        overridable=True,
        priority=20,
    ),
    NutrientSpec(
        key="iron",
        label="Iron",
        unit="mg",
        derivation=FlatBands(IRON_BANDS),
        source=DRI_MICRONUTRIENT_SOURCE,
        intake_field="iron_mg",
        overridable=True,
        priority=30,
        # "Iron needs jump sharply at 7-12 months as birth stores are exhausted"
        # (knowledge-base/nih-dri-micronutrients.md) -- so it leads for infants.
        priority_by_age=((12, 15),),
    ),
    NutrientSpec(
        key="vitamin_d",
        label="Vitamin D",
        unit="IU",
        # The RDA splits at 12 months; the UL also splits at 6 and 47, hence four bands
        # carrying the source table's own two labels.
        derivation=FlatBands(
            (
                Band(6, "0–12 months", 400, "AI", 1000),
                Band(12, "0–12 months", 400, "AI", 1500),
                Band(47, "1–8 years", 600, "RDA", 2500),
                Band(60, "1–8 years", 600, "RDA", 3000),
            )
        ),
        source=DRI_VITAMIN_MINERAL_SOURCE,
        # Intake is supplements and sunlight, so the feeding log cannot observe it; a flag
        # could only ever read `below`, which is noise rather than information.
        intake_field=None,
        not_tracked_reason=(
            "Vitamin D mostly comes from a supplement and sunshine, not from logged food, "
            "so we show the target without a score."
        ),
        priority=40,
        # "Breastfed infants need a supplement" (knowledge-base/nih-dri-micronutrients.md)
        # -- deficiency is the default without one, so it rises for infants.
        priority_by_age=((12, 25),),
    ),
    # Zinc has no NutrientSpec by decision (food-micronutrients): it is a stored
    # food-composition value (zinc_mg) with no reference target for any age or diet.
    NutrientSpec(
        key="calcium",
        label="Calcium",
        unit="mg",
        derivation=FlatBands(
            (
                Band(6, "0–6 months", 200, "AI", 1000),
                Band(12, "7–12 months", 260, "AI", 1500),
                Band(47, "1–3 years", 700, "RDA", 2500),
                Band(60, "4–8 years", 1000, "RDA", 2500),
            )
        ),
        source=DRI_VITAMIN_MINERAL_SOURCE,
        intake_field="calcium_mg",
        priority=60,
    ),
    NutrientSpec(
        key="vitamin_b12",
        label="Vitamin B12",
        unit="µg",
        derivation=FlatBands(
            (
                # No tolerable upper intake level is established for B12.
                Band(6, "0–6 months", 0.4, "AI"),
                Band(12, "7–12 months", 0.5, "AI"),
                Band(47, "1–3 years", 0.9, "RDA"),
                Band(60, "4–8 years", 1.2, "RDA"),
            )
        ),
        source=DRI_VITAMIN_MINERAL_SOURCE,
        # Trackable once the food table carries vitamin_b12_ug (deferred data work). Even
        # then it stays unscored for vegan diets: the table would hold no permitted source,
        # and a permanent `below` cannot tell a supplemented child from an unsupplemented
        # one -- the only distinction that matters.
        intake_field=None,
        untrackable_diets=frozenset({DietPreference.VEGAN}),
        not_tracked_reason=(
            "We can't count vitamin B12 from logged foods yet, so we show the target "
            "without a score."
        ),
        priority=70,
        priority_by_diet=(
            (DietPreference.VEGAN, 25),
            (DietPreference.VEGETARIAN, 45),
        ),
        only_for_diets=frozenset({DietPreference.VEGAN, DietPreference.VEGETARIAN}),
        display_note_by_diet=(
            (
                DietPreference.VEGAN,
                "Every vegan child needs a reliable vitamin B12 source — a supplement or "
                "fortified foods. Please raise it with your pediatrician.",
            ),
            (
                DietPreference.VEGETARIAN,
                "Dairy and eggs usually give vegetarian children enough vitamin B12.",
            ),
        ),
    ),
    NutrientSpec(
        key="dha",
        label="Omega-3 (DHA)",
        # Vestigial: an advisory carries no amount. Non-optional ``unit`` guarantees every
        # numeric row a unit, which is worth one unused value here.
        unit="mg",
        derivation=Advisory(
            text=(
                "Omega-3 DHA supports brain and eye development. Ground flaxseed, chia and "
                "walnuts provide the plant form (ALA), and a DHA supplement from algal oil "
                "may be worth discussing with your pediatrician for a vegan child."
            ),
            source_date="2020",
        ),
        source=AAP_VEGETARIAN_SOURCE,
        priority=80,
        only_for_diets=frozenset({DietPreference.VEGAN}),
    ),
)

SPECS: dict[str, NutrientSpec] = {spec.key: spec for spec in REGISTRY}


# -- selection and evaluation -----------------------------------------------------------------


def _priority(spec: NutrientSpec, age_months: int, diet: DietPreference) -> int:
    """Diet promotion wins over age promotion wins over the default."""
    for preference, value in spec.priority_by_diet:
        if preference is diet:
            return value
    for upper, value in spec.priority_by_age:
        if age_months <= upper:
            return value
    return spec.priority


def displayed_specs(age_months: int, diet: DietPreference) -> tuple[NutrientSpec, ...]:
    """The nutrients shown for this child, most important first.

    Pure and deterministic: the ``key`` tiebreak keeps equal priorities in a stable order,
    because the panel is snapshot-tested and the audit log records the order.
    """
    chosen = (s for s in REGISTRY if s.only_for_diets is None or diet in s.only_for_diets)
    return tuple(sorted(chosen, key=lambda s: (_priority(s, age_months, diet), s.key)))


@dataclass(frozen=True, slots=True)
class EvaluatedTarget:
    """A registry row applied to one child: the number (or advisory) plus provenance."""

    amount: float | None
    band: str
    reference_type: ReferenceType | None
    upper_limit: float | None
    derivation: str
    per_kg: float | None = None
    activity_level: ActivityLevel | None = None
    advisory: str | None = None
    advisory_source_date: str | None = None


def evaluate(spec: NutrientSpec, inputs: TargetInputs) -> EvaluatedTarget:
    """The single dispatch over the derivation styles.

    This replaces the per-nutrient chains that used to live in the gap, override and
    target code: one ``match``, exhaustive over the closed union.
    """
    match spec.derivation:
        case Equation(compute=compute):
            result = compute(inputs)
            # ``max(0, round(...))`` mirrors the calorie tool exactly, so the panel's
            # figure and the tool's figure can never differ by a rounding step.
            return EvaluatedTarget(
                amount=float(max(0, round(result.amount))),
                band=result.band,
                reference_type="EER",
                upper_limit=None,
                derivation=result.derivation,
                activity_level=result.activity_level,
            )
        case PerKgBands(bands=bands):
            band = band_for(bands, inputs.age_months)
            return EvaluatedTarget(
                amount=round(inputs.weight_kg * band.value, 1),
                band=band.label,
                reference_type=band.reference_type,
                upper_limit=band.upper_limit,
                derivation=f"{band.value:g} {spec.unit}/kg × {inputs.weight_kg:g} kg",
                per_kg=band.value,
            )
        case FlatBands(bands=bands):
            band = band_for(bands, inputs.age_months)
            # The table value is already exact as published (e.g. iron 0.27 mg AI);
            # rounding a quoted figure would corrupt it, so only computed styles round.
            return EvaluatedTarget(
                amount=band.value,
                band=band.label,
                reference_type=band.reference_type,
                upper_limit=band.upper_limit,
                derivation=f"DRI table value for {band.label}",
            )
        case Advisory(text=text, source_date=source_date):
            return EvaluatedTarget(
                amount=None,
                band="",
                reference_type=None,
                upper_limit=None,
                derivation="",
                advisory=text,
                advisory_source_date=source_date,
            )
