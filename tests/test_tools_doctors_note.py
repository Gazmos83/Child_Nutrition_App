"""Note-row extraction and deterministic override application (child-notes-restrictions)."""

from typing import get_args

import pytest

from backend.chat import copy
from backend.models.enums import DietPreference, NoteKind, Sex
from backend.nutrition.nutrients import REGISTRY, displayed_specs
from backend.nutrition.targets import (
    calculate_calorie_target,
    calculate_protein_target,
    iron_target,
)
from backend.schemas.tools import (
    UNIT_FOR_NUTRIENT,
    CalorieTargetInput,
    DoctorsNoteOverride,
    GapDetectionRequest,
    NoteRow,
    NutrientTargets,
    OverridableNutrient,
    ProteinTargetInput,
)
from backend.tools.doctors_note import (
    EXTRACT_SYSTEM_PROMPT,
    _parse_reply,
    apply_override,
    apply_overrides,
    extract_notes,
)
from backend.tools.targets_resolution import general_targets, resolve_targets
from tests.fixtures.fake_llm import RecordingChatModel

NOTE = "Please limit intake to 650 kcal per day while we monitor weight gain."
CALORIES_650 = {"nutrient": "calories", "direction": "max", "value": 650, "unit": "kcal"}


def model(*responses: str, fail: str | None = None) -> RecordingChatModel:
    return RecordingChatModel(responses=list(responses), calls=[], fail_with=fail)


def doctor(text: str) -> NoteRow:
    return NoteRow(kind=NoteKind.DOCTOR, text=text)


def preference(text: str) -> NoteRow:
    return NoteRow(kind=NoteKind.PREFERENCE, text=text)


def reply(*rows: dict) -> str:
    import json

    return json.dumps({"rows": list(rows)})


class TestExtractNotes:
    async def test_clear_doctor_target_is_extracted_and_validated(self) -> None:
        llm = model(reply({"row": 1, "target": CALORIES_650, "avoid": []}))
        result = await extract_notes([doctor(NOTE)], llm)
        assert result.status == "applied"
        [target] = result.targets
        assert target.note_index == 0
        assert target.override == DoctorsNoteOverride(
            nutrient="calories", direction="max", value=650, unit="kcal"
        )
        assert result.avoid == [] and result.issues == []

    async def test_prompt_numbers_and_tags_the_rows(self) -> None:
        llm = model(reply())
        await extract_notes([doctor(NOTE), preference("no pork")], llm)
        [messages] = llm.calls
        assert messages[0].content == EXTRACT_SYSTEM_PROMPT
        assert messages[1].content == f"1. [doctor] {NOTE}\n2. [preference] no pork"
        assert '"iron"' in EXTRACT_SYSTEM_PROMPT and "[preference]" in EXTRACT_SYSTEM_PROMPT
        assert "NEVER a target" in EXTRACT_SYSTEM_PROMPT and "never use 0" in EXTRACT_SYSTEM_PROMPT
        assert "dairy" in EXTRACT_SYSTEM_PROMPT and "milk_feed" not in EXTRACT_SYSTEM_PROMPT

    async def test_avoidance_phrase_is_extracted_for_its_row(self) -> None:
        llm = model(reply({"row": 1, "target": None, "avoid": ["dairy"]}))
        result = await extract_notes([doctor("Avoid dairy; recheck in 3 months.")], llm)
        assert result.status == "applied"
        assert result.targets == []
        [item] = result.avoid
        assert (item.note_index, item.phrase) == (0, "dairy")

    async def test_fenced_json_parses(self) -> None:
        llm = model(
            "```json\n"
            + reply(
                {
                    "row": 1,
                    "target": {
                        "nutrient": "iron",
                        "direction": "target",
                        "value": 15,
                        "unit": "mg",
                    },
                    "avoid": [],
                }
            )
            + "\n```"
        )
        result = await extract_notes([doctor("Aim for 15 mg iron daily.")], llm)
        assert result.status == "applied"
        assert result.targets[0].override.nutrient == "iron"

    async def test_nothing_to_apply(self) -> None:
        llm = model(reply({"row": 1, "target": None, "avoid": []}))
        result = await extract_notes([doctor("Recheck in 3 months.")], llm)
        assert result.status == "nothing_to_apply"
        assert result.targets == [] and result.avoid == []

    async def test_preference_target_is_dropped_but_its_avoidances_apply(self) -> None:
        llm = model(reply({"row": 1, "target": CALORIES_650, "avoid": ["pork"]}))
        result = await extract_notes([preference("limit to 650 kcal, no pork")], llm)
        assert result.targets == []
        assert [a.phrase for a in result.avoid] == ["pork"]
        assert [i.detail for i in result.issues] == [copy.NOTE_PREFERENCE_TARGET]
        assert result.status == "applied"

    async def test_two_doctor_rows_on_one_nutrient_are_both_refused(self) -> None:
        llm = model(
            reply(
                {"row": 1, "target": CALORIES_650, "avoid": []},
                {"row": 2, "target": {**CALORIES_650, "value": 700}, "avoid": []},
            )
        )
        result = await extract_notes([doctor(NOTE), doctor("Or 700 kcal at most.")], llm)
        assert result.targets == []
        assert sorted(i.note_index for i in result.issues) == [0, 1]
        assert all("neither was applied" in i.detail for i in result.issues)
        assert result.status == "nothing_to_apply"

    async def test_unknown_nutrient_fails_its_row_only(self) -> None:
        sodium = {"nutrient": "sodium", "direction": "max", "value": 400, "unit": "mg"}
        llm = model(
            reply(
                {"row": 1, "target": sodium, "avoid": []},
                {"row": 2, "target": None, "avoid": ["dairy"]},
            )
        )
        result = await extract_notes(
            [doctor("Limit sodium to 400 mg."), preference("no dairy")], llm
        )
        assert result.targets == []
        assert [i.note_index for i in result.issues] == [0]
        assert result.issues[0].detail == copy.NOTE_TARGET_UNREADABLE
        assert [a.phrase for a in result.avoid] == ["dairy"]
        assert result.status == "applied"

    async def test_direction_synonyms_are_normalised_before_validation(self) -> None:
        """Live failure: the model wrote "limit" for a calorie cap."""
        limit = {"nutrient": "Calories", "direction": "Limit", "value": 600, "unit": "kcal"}
        llm = model(reply({"row": 1, "target": limit, "avoid": []}))
        result = await extract_notes([doctor("limit calories to 600 kcal")], llm)
        [target] = result.targets
        assert target.override.direction == "max" and target.override.value == 600
        assert result.issues == []

    async def test_negated_row_falls_back_to_the_rest_of_the_row(self) -> None:
        """Live failure: the model read "no iron fortified oat cereal" as an iron target of 0."""
        zero_iron = {"nutrient": "iron", "direction": "max", "value": 0, "unit": "mg"}
        llm = model(reply({"row": 1, "target": zero_iron, "avoid": []}))
        result = await extract_notes([doctor("no iron fortified oat cereal")], llm)
        assert result.targets == []
        assert [a.phrase for a in result.avoid] == ["iron fortified oat cereal"]
        assert [i.detail for i in result.issues] == [copy.NOTE_TARGET_UNREADABLE]
        assert result.status == "applied"

    async def test_fallback_only_for_rows_that_open_with_a_negation(self) -> None:
        llm = model(
            reply(
                {"row": 1, "target": None, "avoid": []},
                {"row": 2, "target": None, "avoid": []},
            )
        )
        rows = [doctor("Recheck in 3 months."), preference("Never pork")]
        result = await extract_notes(rows, llm)
        assert [(a.note_index, a.phrase) for a in result.avoid] == [(1, "pork")]

    async def test_mismatched_unit_fails_its_row(self) -> None:
        llm = model(reply({"row": 1, "target": {**CALORIES_650, "unit": "g"}, "avoid": []}))
        result = await extract_notes([doctor(NOTE)], llm)
        assert result.targets == [] and result.issues[0].detail == copy.NOTE_TARGET_UNREADABLE

    async def test_garbage_reply_is_unparsed(self) -> None:
        result = await extract_notes(
            [doctor(NOTE)], model("Sure! The doctor wants fewer calories.")
        )
        assert result.status == "unparsed"

    async def test_wrong_envelope_is_unparsed(self) -> None:
        result = await extract_notes([doctor(NOTE)], model('{"nutrient": "calories"}'))
        assert result.status == "unparsed"

    async def test_model_failure_is_unparsed(self, caplog) -> None:
        result = await extract_notes([doctor(NOTE)], model(fail="upstream 503"))
        assert result.status == "unparsed"
        assert "503" in result.detail
        assert "not applied" in caplog.text

    async def test_no_model_is_unparsed(self) -> None:
        result = await extract_notes([doctor(NOTE)], None)
        assert result.status == "unparsed"
        assert "no language model" in result.detail

    async def test_no_rows_is_not_present_without_model_call(self) -> None:
        llm = model()
        result = await extract_notes([], llm)
        assert result.status == "not_present"
        assert llm.calls == []

    async def test_invented_rows_and_duplicate_phrases_are_ignored(self) -> None:
        llm = model(
            reply(
                {"row": 1, "target": None, "avoid": ["pork", "Pork", "  pork  "]},
                {"row": 7, "target": CALORIES_650, "avoid": ["kale"]},
            )
        )
        result = await extract_notes([preference("no pork")], llm)
        assert [a.phrase for a in result.avoid] == ["pork"]
        assert result.targets == []


class TestParseReply:
    def test_array_rejected(self) -> None:
        with pytest.raises(ValueError):
            _parse_reply("[1, 2]")

    def test_extra_keys_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 -- pydantic ValidationError or ValueError
            _parse_reply('{"rows": [], "notes": []}')


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


class TestApplyOverrides:
    def test_three_nutrients_apply_independently(self) -> None:
        general = targets_for(8, 8.5)
        applied, outcomes = apply_overrides(
            general,
            [
                DoctorsNoteOverride(nutrient="calories", direction="max", value=650, unit="kcal"),
                DoctorsNoteOverride(nutrient="protein", direction="min", value=14, unit="g"),
                DoctorsNoteOverride(nutrient="iron", direction="target", value=15, unit="mg"),
            ],
        )
        assert [o.nutrient for o in outcomes] == ["calories", "protein", "iron"]
        assert all(o.conflict for o in outcomes)
        assert applied.calories.calories == 650
        assert applied.protein.protein_g == 14.0
        assert applied.iron.iron_mg == 15.0

    def test_no_overrides_means_no_outcomes(self) -> None:
        general = targets_for(8, 8.5)
        applied, outcomes = apply_overrides(general, [])
        assert applied == general and outcomes == []


class TestPromptDerivation:
    """Prompt and unit map derive from the registry's overridable rows (day-9 task 3.2)."""

    def test_prompt_names_exactly_the_overridable_nutrients(self) -> None:
        for spec in REGISTRY:
            assert (f'"{spec.key}"' in EXTRACT_SYSTEM_PROMPT) == spec.overridable, spec.key

    def test_unit_map_is_the_overridable_rows(self) -> None:
        assert UNIT_FOR_NUTRIENT == {"calories": "kcal", "protein": "g", "iron": "mg"}
        assert {s.key: s.unit for s in REGISTRY if s.overridable} == UNIT_FOR_NUTRIENT


class TestOverrideBoundary:
    """doctors-note-override delta spec: the overridable set does not follow the displayed set."""

    def displayed_child(self, age: int, note: str | None = None) -> GapDetectionRequest:
        return GapDetectionRequest(
            age_months=age,
            weight_kg=12.0,
            sex=Sex.FEMALE,
            notes=[doctor(note)] if note else [],
        )

    async def test_calcium_note_is_rejected_like_any_unknown_nutrient(self) -> None:
        calcium = {"nutrient": "calcium", "direction": "max", "value": 500, "unit": "mg"}
        llm = model(reply({"row": 1, "target": calcium, "avoid": []}))
        result = await extract_notes([doctor("Limit calcium to 500 mg daily.")], llm)
        assert result.status == "nothing_to_apply"
        assert result.targets == []
        assert result.issues[0].detail == copy.NOTE_TARGET_UNREADABLE

    async def test_calcium_note_leaves_the_displayed_target_general(self) -> None:
        request = self.displayed_child(24, note="Limit calcium to 500 mg daily.")
        calcium = {"nutrient": "calcium", "direction": "max", "value": 500, "unit": "mg"}
        llm = model(reply({"row": 1, "target": calcium, "avoid": []}))
        targets, extraction, overrides = await resolve_targets(request, llm)
        assert extraction.status == "nothing_to_apply"
        assert overrides == []
        # Calcium is displayed with the general 1-3 years RDA, not the note's 500.
        assert targets.require("calcium").amount == 700.0
        assert targets == general_targets(request)

    def test_overridable_set_stays_three_as_the_displayed_set_widens(self) -> None:
        overridable = {s.key for s in REGISTRY if s.overridable}
        assert overridable == {"calories", "protein", "iron"}
        assert overridable == set(get_args(OverridableNutrient))
        assert len(displayed_specs(30, DietPreference.VEGAN)) > 3

    def test_override_on_a_widened_set_changes_only_the_named_row(self) -> None:
        general = general_targets(self.displayed_child(8))
        assert len(general.items) == 6  # calories, iron, protein, vitamin D, zinc, calcium
        applied, outcome = apply_override(
            general,
            DoctorsNoteOverride(nutrient="calories", direction="max", value=650, unit="kcal"),
        )
        assert outcome.conflict is True
        assert applied.amount_of("calories") == 650.0
        untouched = [row for row in applied.items if row.nutrient != "calories"]
        assert untouched == [row for row in general.items if row.nutrient != "calories"]
