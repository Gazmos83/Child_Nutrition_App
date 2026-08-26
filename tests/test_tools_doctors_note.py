"""Doctor's-note extraction and deterministic override application (tasks 4.1, 4.2)."""

import pytest

from backend.models.enums import Sex
from backend.nutrition.targets import (
    calculate_calorie_target,
    calculate_protein_target,
    iron_target,
)
from backend.schemas.tools import (
    CalorieTargetInput,
    DoctorsNoteOverride,
    NutrientTargets,
    ProteinTargetInput,
)
from backend.tools.doctors_note import (
    EXTRACT_SYSTEM_PROMPT,
    _parse_override,
    apply_override,
    extract_override,
)
from tests.fixtures.fake_llm import RecordingChatModel

NOTE = "Please limit intake to 650 kcal per day while we monitor weight gain."


def model(*responses: str, fail: str | None = None) -> RecordingChatModel:
    return RecordingChatModel(responses=list(responses), calls=[], fail_with=fail)


class TestExtractOverride:
    async def test_clear_note_is_extracted_and_validated(self) -> None:
        llm = model('{"nutrient": "calories", "direction": "max", "value": 650, "unit": "kcal"}')
        result = await extract_override(NOTE, llm)
        assert result.status == "applied"
        assert result.override == DoctorsNoteOverride(
            nutrient="calories", direction="max", value=650, unit="kcal"
        )

    async def test_prompt_contains_note_and_instructions(self) -> None:
        llm = model("null")
        await extract_override(NOTE, llm)
        [messages] = llm.calls
        assert messages[0].content == EXTRACT_SYSTEM_PROMPT
        assert messages[1].content == NOTE
        assert "null" in EXTRACT_SYSTEM_PROMPT and '"iron"' in EXTRACT_SYSTEM_PROMPT

    async def test_fenced_json_parses(self) -> None:
        llm = model(
            '```json\n{"nutrient": "iron", "direction": "target", "value": 15, "unit": "mg"}\n```'
        )
        result = await extract_override("Aim for 15 mg iron daily.", llm)
        assert result.status == "applied"
        assert result.override.nutrient == "iron" and result.override.value == 15

    async def test_null_means_no_numeric_target(self) -> None:
        result = await extract_override("Avoid dairy; recheck in 3 months.", model("null"))
        assert result.status == "no_numeric_target"
        assert result.override is None
        assert result.detail

    async def test_unknown_nutrient_is_unparsed(self) -> None:
        llm = model('{"nutrient": "sodium", "direction": "max", "value": 400, "unit": "mg"}')
        result = await extract_override("Limit sodium to 400 mg.", llm)
        assert result.status == "unparsed"
        assert result.override is None
        assert "nutrient" in result.detail

    async def test_mismatched_unit_is_unparsed(self) -> None:
        llm = model('{"nutrient": "calories", "direction": "max", "value": 650, "unit": "g"}')
        result = await extract_override(NOTE, llm)
        assert result.status == "unparsed"
        assert "kcal" in result.detail

    async def test_garbage_reply_is_unparsed(self) -> None:
        result = await extract_override(NOTE, model("Sure! The doctor wants fewer calories."))
        assert result.status == "unparsed"

    async def test_model_failure_is_unparsed(self, caplog) -> None:
        result = await extract_override(NOTE, model(fail="upstream 503"))
        assert result.status == "unparsed"
        assert "503" in result.detail
        assert "not applied" in caplog.text

    async def test_no_model_is_unparsed(self) -> None:
        result = await extract_override(NOTE, None)
        assert result.status == "unparsed"
        assert "no language model" in result.detail

    @pytest.mark.parametrize("note", [None, "", "   "])
    async def test_missing_note_is_not_present_without_model_call(self, note) -> None:
        llm = model()
        result = await extract_override(note, llm)
        assert result.status == "not_present"
        assert llm.calls == []


class TestParseOverride:
    def test_json_null_inside_object_text(self) -> None:
        assert _parse_override(" null ") is None

    def test_array_rejected(self) -> None:
        with pytest.raises(ValueError):
            _parse_override("[1, 2]")


def targets_for(age: int, weight: float) -> NutrientTargets:
    return NutrientTargets(
        calories=calculate_calorie_target(
            CalorieTargetInput(age_months=age, weight_kg=weight, sex=Sex.FEMALE)
        ),
        protein=calculate_protein_target(ProteinTargetInput(age_months=age, weight_kg=weight)),
        iron=iron_target(age),
    )


class TestApplyOverride:
    def test_max_below_general_calories_note_wins(self) -> None:
        general = targets_for(8, 8.5)  # 89*8.5-100+22 = 678 kcal
        assert general.calories.calories == 678
        applied, outcome = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="max", value=650, unit="kcal"),
        )
        assert outcome.conflict is True
        assert outcome.source == "doctors_note"
        assert outcome.general_value == 678 and outcome.applied_value == 650
        assert applied.calories.calories == 650
        assert "doctor's note" in applied.calories.source
        # Other targets untouched.
        assert applied.protein == general.protein and applied.iron == general.iron

    def test_max_above_general_no_conflict(self) -> None:
        general = targets_for(8, 8.5)
        applied, outcome = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="max", value=800, unit="kcal"),
        )
        assert outcome.conflict is False
        assert outcome.source == "general_target"
        assert outcome.nutrient == "calories"
        assert applied == general

    def test_target_within_tolerance_no_conflict(self) -> None:
        general = targets_for(8, 8.5)
        _, outcome = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="target", value=690, unit="kcal"),
        )
        assert outcome.conflict is False  # 678 vs 690 is < 5 %

    def test_target_beyond_tolerance_note_wins(self) -> None:
        general = targets_for(8, 8.5)
        applied, outcome = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="target", value=600, unit="kcal"),
        )
        assert outcome.conflict is True
        assert applied.calories.calories == 600

    def test_min_above_general_protein_note_wins(self) -> None:
        general = targets_for(8, 8.5)  # 1.2 * 8.5 = 10.2 g
        applied, outcome = apply_override(
            general, DoctorsNoteOverride(nutrient="protein", direction="min", value=14, unit="g")
        )
        assert outcome.conflict is True
        assert applied.protein.protein_g == 14.0
        assert applied.calories == general.calories

    def test_iron_target_override(self) -> None:
        general = targets_for(20, 11)  # 7 mg
        applied, outcome = apply_override(
            general, DoctorsNoteOverride(nutrient="iron", direction="target", value=15, unit="mg")
        )
        assert outcome.conflict is True
        assert applied.iron.iron_mg == 15.0

    def test_none_override_no_conflict_no_override(self) -> None:
        general = targets_for(8, 8.5)
        applied, outcome = apply_override(general, None)
        assert applied == general
        assert outcome.conflict is False
        assert outcome.nutrient is None and outcome.applied_value is None

    def test_values_are_never_blended(self) -> None:
        general = targets_for(8, 8.5)
        applied, _ = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="max", value=500, unit="kcal"),
        )
        assert applied.calories.calories in {500, general.calories.calories}
        assert applied.calories.calories == 500
