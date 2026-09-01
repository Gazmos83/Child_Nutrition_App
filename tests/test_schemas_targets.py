"""The uniform target row enforces its invariants at the boundary (day-9 design Decision 3).

A display-only nutrient acquiring a flag must be a validation error, never a rendered bug.
"""

import pytest
from pydantic import ValidationError

from backend.schemas.tools import (
    CalorieTargetResult,
    IronTargetResult,
    NutrientTarget,
    NutrientTargets,
    ProteinTargetResult,
)


def row(**overrides) -> NutrientTarget:
    base = dict(
        nutrient="calcium",
        label="Calcium",
        unit="mg",
        amount=700.0,
        reference_type="RDA",
        band="1–3 years",
        source="NIH ODS tables (2011)",
        tracked=True,
    )
    return NutrientTarget(**{**base, **overrides})


def legacy_targets() -> NutrientTargets:
    return NutrientTargets(
        calories=CalorieTargetResult(
            calories=850, band="7–12 months", formula="EER = test", source="DRI (2005)"
        ),
        protein=ProteinTargetResult(
            protein_g=10.2,
            grams_per_kg=1.2,
            reference_type="RDA",
            band="7–12 months",
            source="DRI (2005)",
        ),
        iron=IronTargetResult(
            iron_mg=11.0, reference_type="RDA", band="7–12 months", source="DRI (2001)"
        ),
    )


class TestNutrientTargetInvariants:
    def test_a_valid_tracked_row_passes(self) -> None:
        assert row().flag is None

    def test_amount_and_advisory_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of amount or advisory"):
            row(advisory="also has text", advisory_source_date="2020")
        with pytest.raises(ValidationError, match="exactly one of amount or advisory"):
            row(amount=None)

    def test_an_advisory_carries_its_publication_date(self) -> None:
        with pytest.raises(ValidationError, match="publication date"):
            row(amount=None, tracked=False, advisory="guidance", advisory_source_date=None)

    def test_a_tracked_row_needs_an_amount(self) -> None:
        # amount=None alone already violates amount-or-advisory; with an advisory present
        # the tracked invariant is what rejects it.
        with pytest.raises(ValidationError, match="tracked nutrient must have a numeric"):
            row(amount=None, advisory="text", advisory_source_date="2020", tracked=True)

    @pytest.mark.parametrize(
        "extra", [{"intake_average": 320.0}, {"ratio": 0.46}, {"flag": "below"}]
    )
    def test_a_display_only_row_can_never_carry_intake_or_a_flag(self, extra: dict) -> None:
        with pytest.raises(ValidationError, match="can never carry intake or a flag"):
            row(tracked=False, not_tracked_reason="no per-food data yet", **extra)

    def test_an_unscored_numeric_row_carries_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="parent-facing reason"):
            row(tracked=False, not_tracked_reason=None)

    def test_a_display_only_row_with_a_reason_passes(self) -> None:
        result = row(tracked=False, not_tracked_reason="no per-food data yet")
        assert result.intake_average is None and result.flag is None


class TestNutrientTargetsContainer:
    def test_duplicate_nutrients_are_rejected(self) -> None:
        targets = legacy_targets()
        with pytest.raises(ValidationError, match="at most once"):
            NutrientTargets(items=targets.items + (targets.items[0],))

    def test_the_composed_three_are_required(self) -> None:
        targets = legacy_targets()
        without_iron = tuple(r for r in targets.items if r.nutrient != "iron")
        with pytest.raises(ValidationError, match="missing \\['iron'\\]"):
            NutrientTargets(items=without_iron)


class TestLegacyFacade:
    """The Day 4 shape keeps working, byte for byte, until the façade is removed."""

    def test_legacy_construction_round_trips(self) -> None:
        targets = legacy_targets()
        assert targets.calories.calories == 850
        assert targets.protein.protein_g == 10.2 and targets.protein.grams_per_kg == 1.2
        assert targets.iron.iron_mg == 11.0
        assert [r.nutrient for r in targets.items] == ["calories", "protein", "iron"]

    def test_serialization_is_a_superset_of_day_4(self) -> None:
        dumped = legacy_targets().model_dump(mode="json")
        assert {"calories", "protein", "iron", "items"} <= dumped.keys()
        assert dumped["calories"]["calories"] == 850
        # and a dump revalidates to an identical model (items wins over the legacy keys)
        assert NutrientTargets.model_validate(dumped) == legacy_targets()

    def test_model_copy_with_a_legacy_key_updates_the_row(self) -> None:
        """A computed property would silently swallow this; the override must not."""
        targets = legacy_targets()
        capped = targets.model_copy(
            update={"calories": targets.calories.model_copy(update={"calories": 650})}
        )
        assert capped.calories.calories == 650
        assert capped.require("calories").amount == 650.0
        assert capped.require("protein").amount == 10.2  # untouched rows survive

    def test_with_amount_updates_row_and_facade_together(self) -> None:
        targets = legacy_targets()
        overridden = targets.with_amount(
            "iron", 9.0, source="doctor's note (overrides general target)"
        )
        assert overridden.require("iron").amount == 9.0
        assert overridden.iron.iron_mg == 9.0
        assert overridden.iron.source == "doctor's note (overrides general target)"
