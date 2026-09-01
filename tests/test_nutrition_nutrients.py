"""The nutrient registry: band values, age/diet selection, and the evaluate dispatch.

Every expected figure here is typed by hand from ``knowledge-base/nih-dri-micronutrients.md``
-- never copied from the registry -- so a transcription slip in the registry fails a test
instead of reaching a parent.
"""

from pathlib import Path
from typing import get_args

import pytest

from backend.models.enums import ActivityLevel, DietPreference, Sex
from backend.nutrition.foods import FoodItem
from backend.nutrition.nutrients import (
    ENERGY_BANDS,
    IRON_BANDS,
    REGISTRY,
    SPECS,
    Advisory,
    Equation,
    FlatBands,
    NutrientKey,
    PerKgBands,
    TargetInputs,
    band_for,
    displayed_specs,
    evaluate,
)
from backend.nutrition.targets import calculate_calorie_target
from backend.schemas.tools import (
    MAX_AGE_MONTHS,
    CalorieTargetInput,
    NutrientTotals,
    OverridableNutrient,
)


def inputs(
    age_months: int,
    weight_kg: float = 10.0,
    sex: Sex = Sex.FEMALE,
    height_cm: float | None = None,
) -> TargetInputs:
    return TargetInputs(
        age_months=age_months,
        weight_kg=weight_kg,
        sex=sex,
        height_cm=height_cm,
        activity_level=ActivityLevel.LOW_ACTIVE,
    )


class TestBandBoundaries:
    """Values, reference types and ULs at both sides of every band edge (6/7, 12/13, 47/48, 60)."""

    @pytest.mark.parametrize(
        ("age", "amount", "ref", "upper"),
        [
            (0, 0.27, "AI", 40.0),
            (6, 0.27, "AI", 40.0),
            (7, 11.0, "RDA", 40.0),
            (12, 11.0, "RDA", 40.0),
            (13, 7.0, "RDA", 40.0),
            (47, 7.0, "RDA", 40.0),
            (48, 10.0, "RDA", 40.0),
            (60, 10.0, "RDA", 40.0),
        ],
    )
    def test_iron(self, age: int, amount: float, ref: str, upper: float) -> None:
        result = evaluate(SPECS["iron"], inputs(age))
        assert (result.amount, result.reference_type, result.upper_limit) == (amount, ref, upper)

    @pytest.mark.parametrize(
        ("age", "per_kg", "ref"),
        [
            (0, 1.52, "AI"),
            (6, 1.52, "AI"),
            (7, 1.2, "RDA"),
            (12, 1.2, "RDA"),
            (13, 1.05, "RDA"),
            (47, 1.05, "RDA"),
            (48, 0.95, "RDA"),
            (60, 0.95, "RDA"),
        ],
    )
    def test_protein(self, age: int, per_kg: float, ref: str) -> None:
        result = evaluate(SPECS["protein"], inputs(age, weight_kg=10.0))
        assert result.per_kg == per_kg
        assert result.amount == round(10.0 * per_kg, 1)
        assert result.reference_type == ref

    @pytest.mark.parametrize(
        ("age", "amount", "ref", "upper"),
        [
            (0, 400, "AI", 1000),
            (6, 400, "AI", 1000),
            (7, 400, "AI", 1500),
            (12, 400, "AI", 1500),
            (13, 600, "RDA", 2500),
            (47, 600, "RDA", 2500),
            (48, 600, "RDA", 3000),
            (60, 600, "RDA", 3000),
        ],
    )
    def test_vitamin_d(self, age: int, amount: float, ref: str, upper: float) -> None:
        result = evaluate(SPECS["vitamin_d"], inputs(age))
        assert (result.amount, result.reference_type, result.upper_limit) == (amount, ref, upper)

    @pytest.mark.parametrize(
        ("age", "amount", "ref", "upper"),
        [
            (0, 2.0, "AI", 4),
            (6, 2.0, "AI", 4),
            (7, 3.0, "RDA", 5),
            (12, 3.0, "RDA", 5),
            (13, 3.0, "RDA", 7),
            (47, 3.0, "RDA", 7),
            (48, 5.0, "RDA", 12),
            (60, 5.0, "RDA", 12),
        ],
    )
    def test_zinc(self, age: int, amount: float, ref: str, upper: float) -> None:
        result = evaluate(SPECS["zinc"], inputs(age))
        assert (result.amount, result.reference_type, result.upper_limit) == (amount, ref, upper)

    @pytest.mark.parametrize(
        ("age", "amount", "ref", "upper"),
        [
            (0, 200, "AI", 1000),
            (6, 200, "AI", 1000),
            (7, 260, "AI", 1500),
            (12, 260, "AI", 1500),
            (13, 700, "RDA", 2500),
            (47, 700, "RDA", 2500),
            (48, 1000, "RDA", 2500),
            (60, 1000, "RDA", 2500),
        ],
    )
    def test_calcium(self, age: int, amount: float, ref: str, upper: float) -> None:
        result = evaluate(SPECS["calcium"], inputs(age))
        assert (result.amount, result.reference_type, result.upper_limit) == (amount, ref, upper)

    @pytest.mark.parametrize(
        ("age", "amount", "ref"),
        [
            (0, 0.4, "AI"),
            (6, 0.4, "AI"),
            (7, 0.5, "AI"),
            (12, 0.5, "AI"),
            (13, 0.9, "RDA"),
            (47, 0.9, "RDA"),
            (48, 1.2, "RDA"),
            (60, 1.2, "RDA"),
        ],
    )
    def test_vitamin_b12(self, age: int, amount: float, ref: str) -> None:
        result = evaluate(SPECS["vitamin_b12"], inputs(age))
        assert (result.amount, result.reference_type) == (amount, ref)
        assert result.upper_limit is None  # no UL is established for B12

    def test_above_the_last_band_raises(self) -> None:
        with pytest.raises(ValueError, match="above the last band"):
            band_for(IRON_BANDS, 61)


class TestDisplayOrder:
    @pytest.mark.parametrize(
        ("age", "diet", "expected"),
        [
            (
                9,
                DietPreference.OMNIVORE,
                ("calories", "iron", "protein", "vitamin_d", "zinc", "calcium"),
            ),
            (
                3,
                DietPreference.OMNIVORE,
                ("calories", "iron", "protein", "vitamin_d", "zinc", "calcium"),
            ),
            (
                30,
                DietPreference.OMNIVORE,
                ("calories", "protein", "iron", "vitamin_d", "zinc", "calcium"),
            ),
            (
                48,
                DietPreference.PESCATARIAN,
                ("calories", "protein", "iron", "vitamin_d", "zinc", "calcium"),
            ),
            (
                30,
                DietPreference.VEGETARIAN,
                ("calories", "protein", "iron", "vitamin_d", "vitamin_b12", "zinc", "calcium"),
            ),
            (
                30,
                DietPreference.VEGAN,
                (
                    "calories",
                    "protein",
                    "vitamin_b12",
                    "iron",
                    "vitamin_d",
                    "zinc",
                    "calcium",
                    "dha",
                ),
            ),
            (
                9,
                DietPreference.VEGAN,
                (
                    "calories",
                    "iron",
                    "protein",
                    "vitamin_b12",
                    "vitamin_d",
                    "zinc",
                    "calcium",
                    "dha",
                ),
            ),
        ],
    )
    def test_membership_and_order(
        self, age: int, diet: DietPreference, expected: tuple[str, ...]
    ) -> None:
        assert tuple(s.key for s in displayed_specs(age, diet)) == expected

    def test_iron_leads_for_infants(self) -> None:
        keys = [s.key for s in displayed_specs(9, DietPreference.OMNIVORE)]
        assert keys.index("iron") < keys.index("protein")

    def test_b12_absent_for_omnivore_and_pescatarian(self) -> None:
        for diet in (DietPreference.OMNIVORE, DietPreference.PESCATARIAN):
            keys = {s.key for s in displayed_specs(30, diet)}
            assert "vitamin_b12" not in keys
            assert "dha" not in keys

    def test_selection_is_deterministic(self) -> None:
        first = displayed_specs(30, DietPreference.VEGAN)
        second = displayed_specs(30, DietPreference.VEGAN)
        assert first == second

    def test_values_do_not_vary_by_diet(self) -> None:
        """There is no vegan RDA: a nutrient present for two diets has identical figures."""
        for diet in DietPreference:
            for spec in displayed_specs(24, diet):
                base = evaluate(spec, inputs(24))
                assert base == evaluate(SPECS[spec.key], inputs(24))


class TestDerivationStyles:
    def test_protein_scales_with_weight(self) -> None:
        light = evaluate(SPECS["protein"], inputs(24, weight_kg=10.0))
        heavy = evaluate(SPECS["protein"], inputs(24, weight_kg=14.0))
        assert light.amount == 10.5 and heavy.amount == 14.7
        assert light.per_kg == heavy.per_kg == 1.05
        assert "1.05 g/kg × 10 kg" in light.derivation

    def test_iron_ignores_weight(self) -> None:
        assert evaluate(SPECS["iron"], inputs(9, weight_kg=7.0)) == evaluate(
            SPECS["iron"], inputs(9, weight_kg=11.0)
        )

    def test_calories_match_the_tool_exactly(self) -> None:
        """The anti-rounding-drift guarantee: same figure as calculate_calorie_target."""
        result = evaluate(SPECS["calories"], inputs(9, weight_kg=8.5))
        tool = calculate_calorie_target(
            CalorieTargetInput(age_months=9, weight_kg=8.5, sex=Sex.FEMALE)
        )
        assert result.amount == tool.calories == round(89 * 8.5 - 100 + 22)
        assert result.reference_type == "EER"
        assert result.activity_level is None
        assert "EER =" in result.derivation

    def test_calories_carry_activity_level_from_36_months(self) -> None:
        result = evaluate(
            SPECS["calories"], inputs(48, weight_kg=16.0, sex=Sex.MALE, height_cm=100.0)
        )
        tool = calculate_calorie_target(
            CalorieTargetInput(
                age_months=48,
                weight_kg=16.0,
                sex=Sex.MALE,
                height_cm=100.0,
                activity_level=ActivityLevel.LOW_ACTIVE,
            )
        )
        assert result.amount == tool.calories
        assert result.activity_level is ActivityLevel.LOW_ACTIVE

    def test_advisory_carries_text_and_no_number(self) -> None:
        result = evaluate(SPECS["dha"], inputs(30))
        assert result.amount is None
        assert result.advisory and "algal oil" in result.advisory
        assert result.advisory_source_date == "2020"

    def test_numeric_rows_never_carry_an_advisory(self) -> None:
        for spec in REGISTRY:
            if spec.key == "dha":
                continue
            result = evaluate(spec, inputs(24, height_cm=90.0))
            assert result.advisory is None
            assert result.amount is not None


KNOWLEDGE_BASE = Path(__file__).parent.parent / "knowledge-base"
MICRONUTRIENT_DOC = (KNOWLEDGE_BASE / "nih-dri-micronutrients.md").read_text(encoding="utf-8")
ENERGY_PROTEIN_DOC = (KNOWLEDGE_BASE / "nih-dri-energy-and-protein.md").read_text(encoding="utf-8")


def _variants(value: float) -> set[str]:
    """How the knowledge base might print the number, e.g. 1000 as '1,000'."""
    out = {f"{value:g}"}
    if value == int(value):
        out.add(f"{int(value):,}")
    return out


def _cited(value: float, unit: str, doc: str) -> bool:
    return any(f"{variant} {unit}" in doc for variant in _variants(value))


class TestKnowledgeBaseParity:
    """Every registry figure appears verbatim in the corpus the RAG answers cite.

    This makes hard rule 5 mechanical: a target the panel shows and a figure a cited answer
    quotes cannot disagree, because both trace to the same document -- and a transcription
    slip in the registry fails here instead of reaching a parent.
    """

    @pytest.mark.parametrize(
        "spec", [s for s in REGISTRY if isinstance(s.derivation, FlatBands)], ids=lambda s: s.key
    )
    def test_flat_band_values_and_upper_limits_are_cited(self, spec) -> None:
        for band in spec.derivation.bands:
            assert _cited(band.value, spec.unit, MICRONUTRIENT_DOC), (
                f"{spec.key}: {band.value} {spec.unit} ({band.label}) not found in "
                "nih-dri-micronutrients.md"
            )
            if band.upper_limit is not None:
                assert _cited(band.upper_limit, spec.unit, MICRONUTRIENT_DOC), (
                    f"{spec.key}: UL {band.upper_limit} {spec.unit} ({band.label}) not found "
                    "in nih-dri-micronutrients.md"
                )

    def test_protein_per_kg_values_are_cited(self) -> None:
        derivation = SPECS["protein"].derivation
        assert isinstance(derivation, PerKgBands)
        for band in derivation.bands:
            assert _cited(band.value, "g/kg", ENERGY_PROTEIN_DOC), (
                f"protein: {band.value} g/kg ({band.label}) not found in "
                "nih-dri-energy-and-protein.md"
            )

    def test_energy_growth_constants_are_cited(self) -> None:
        for _, _, growth in ENERGY_BANDS:
            assert f"{growth}" in ENERGY_PROTEIN_DOC

    def test_an_altered_value_is_rejected(self) -> None:
        """The failure mode, pinned: a figure the corpus does not contain fails parity."""
        assert not _cited(999.0, "mg", MICRONUTRIENT_DOC)
        assert not _cited(0.28, "mg", MICRONUTRIENT_DOC)

    def test_thousands_separator_is_handled(self) -> None:
        """Calcium's 1,000 mg is written with a separator in the source table."""
        assert _cited(1000, "mg", MICRONUTRIENT_DOC)
        assert "1000 mg" not in MICRONUTRIENT_DOC  # only the separated spelling exists


class TestRegistryInvariants:
    """Structural guarantees the rest of the system leans on."""

    def test_keys_are_unique_and_match_the_literal(self) -> None:
        keys = [spec.key for spec in REGISTRY]
        assert len(keys) == len(set(keys))
        assert set(keys) == set(get_args(NutrientKey))
        assert SPECS.keys() == set(keys)

    def test_every_intake_field_is_a_real_attribute(self) -> None:
        """A dangling field name would silently sum nothing; catch it at the registry."""
        for spec in REGISTRY:
            if spec.intake_field is not None:
                assert spec.intake_field in NutrientTotals.model_fields, spec.key
                assert spec.intake_field in FoodItem.model_fields, spec.key

    def test_overridable_set_equals_the_doctors_note_union(self) -> None:
        """The extraction prompt and validation derive from ``overridable``; the closed
        ``OverridableNutrient`` literal must name exactly the same nutrients."""
        overridable = {spec.key for spec in REGISTRY if spec.overridable}
        assert overridable == set(get_args(OverridableNutrient))

    def test_advisory_rows_are_never_trackable(self) -> None:
        for spec in REGISTRY:
            if isinstance(spec.derivation, Advisory):
                assert spec.intake_field is None
                for diet in DietPreference:
                    assert not spec.tracked_for(diet)

    def test_band_tables_are_increasing_and_reach_the_maximum_age(self) -> None:
        for spec in REGISTRY:
            bands = getattr(spec.derivation, "bands", None)
            if bands is None:
                continue
            uppers = [band.upper_age_months for band in bands]
            assert uppers == sorted(uppers) and len(uppers) == len(set(uppers)), spec.key
            assert uppers[-1] == MAX_AGE_MONTHS, spec.key

    def test_energy_band_labels_reach_the_maximum_age(self) -> None:
        derivation = SPECS["calories"].derivation
        assert isinstance(derivation, Equation)
        assert derivation.band_labels[-1][0] == MAX_AGE_MONTHS

    def test_a_nutrient_not_tracked_carries_a_parent_facing_reason(self) -> None:
        """The panel explains an unscored number instead of leaving a bare gap."""
        for spec in REGISTRY:
            if isinstance(spec.derivation, Advisory):
                continue  # advisories communicate through their text
            if any(not spec.tracked_for(diet) for diet in DietPreference):
                assert spec.not_tracked_reason, spec.key

    def test_every_source_names_its_provenance(self) -> None:
        for spec in REGISTRY:
            assert spec.source and any(ch.isdigit() for ch in spec.source), (
                f"{spec.key}: source must carry a publication date (hard rule 5)"
            )
