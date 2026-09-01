"""``general_targets`` over the registry, and the anti-drift guarantee (day-9 tasks 2.3, 2.5).

Every expected figure is typed by hand from the knowledge-base documents -- never read from
``REGISTRY`` -- so a registry slip fails here instead of reaching a parent.
"""

from backend.models.enums import DietPreference, Sex
from backend.schemas.tools import GapDetectionRequest
from backend.tools.targets_resolution import general_targets, resolve_targets
from tests.fixtures.fake_llm import RecordingChatModel


def child(
    age_months: int = 8,
    weight_kg: float = 8.5,
    diet: DietPreference = DietPreference.OMNIVORE,
    doctors_note: str | None = None,
) -> GapDetectionRequest:
    return GapDetectionRequest(
        age_months=age_months,
        weight_kg=weight_kg,
        sex=Sex.FEMALE,
        diet_preference=diet,
        doctors_note=doctors_note,
    )


class TestGeneralTargets:
    def test_infant_omnivore_set_order_and_figures(self) -> None:
        targets = general_targets(child())
        assert tuple(row.nutrient for row in targets.items) == (
            "calories",
            "iron",
            "protein",
            "vitamin_d",
            "zinc",
            "calcium",
        )
        # 89 × 8.5 − 100 + 22 = 678 kcal (2005 DRI infant equation)
        assert targets.amount_of("calories") == 678.0
        # 1.2 g/kg × 8.5 kg (7-12 months RDA)
        protein = targets.require("protein")
        assert protein.amount == 10.2 and protein.per_kg == 1.2
        iron = targets.require("iron")
        assert iron.amount == 11.0 and iron.upper_limit == 40.0 and iron.band == "7–12 months"
        calcium = targets.require("calcium")
        assert calcium.amount == 260 and calcium.tracked is True

    def test_unscored_rows_carry_a_reason(self) -> None:
        targets = general_targets(child())
        vitamin_d = targets.require("vitamin_d")
        assert vitamin_d.amount == 400 and vitamin_d.unit == "IU"
        assert vitamin_d.tracked is False and vitamin_d.not_tracked_reason
        zinc = targets.require("zinc")
        assert zinc.amount == 3 and zinc.tracked is False and zinc.not_tracked_reason

    def test_vegan_toddler_gains_b12_and_the_dha_advisory(self) -> None:
        targets = general_targets(child(age_months=30, weight_kg=13.0, diet=DietPreference.VEGAN))
        b12 = targets.require("vitamin_b12")
        assert b12.amount == 0.9 and b12.unit == "µg"  # 1-3 years RDA
        assert b12.tracked is False
        assert "supplement" in b12.display_note and "pediatrician" in b12.display_note
        dha = targets.require("dha")
        assert dha.amount is None and dha.advisory and dha.advisory_source_date == "2020"
        assert dha.tracked is False

    def test_diet_never_changes_a_number(self) -> None:
        omnivore = general_targets(child(age_months=30, weight_kg=13.0))
        vegan = general_targets(child(age_months=30, weight_kg=13.0, diet=DietPreference.VEGAN))
        shared = {row.nutrient for row in omnivore.items} & {row.nutrient for row in vegan.items}
        assert shared  # the diets overlap on the core set
        for key in shared:
            assert omnivore.require(key).amount == vegan.require(key).amount, key

    def test_facade_reads_the_same_rows(self) -> None:
        targets = general_targets(child())
        assert targets.calories.calories == 678
        assert targets.protein.protein_g == 10.2
        assert targets.iron.iron_mg == 11.0


class TestAntiDrift:
    """The general target from the registry equals the resolved target (design risk note)."""

    async def test_without_a_note_resolved_equals_general(self) -> None:
        request = child()
        general = general_targets(request)
        resolved, extraction, override = await resolve_targets(request, None)
        assert resolved == general
        assert resolved.amount_of("calories") == general.amount_of("calories") == 678.0
        assert extraction.status == "not_present"
        assert override.conflict is False

    async def test_with_a_note_only_the_named_row_moves(self) -> None:
        request = child(doctors_note="Limit to 650 kcal per day.")
        reply = '{"nutrient": "calories", "direction": "max", "value": 650, "unit": "kcal"}'
        llm = RecordingChatModel(responses=[reply], calls=[])
        general = general_targets(request)
        resolved, extraction, override = await resolve_targets(request, llm)
        assert extraction.status == "applied"
        assert override.conflict is True and override.source == "doctors_note"
        assert general.amount_of("calories") == 678.0
        assert resolved.amount_of("calories") == 650.0
        untouched = [row for row in resolved.items if row.nutrient != "calories"]
        assert untouched == [row for row in general.items if row.nutrient != "calories"]
