"""detect_nutrient_gaps over a client-held log (change 2 task 2.3; nutrient-gap-detection spec)."""

import json
import logging
from datetime import UTC, date, datetime, timedelta

import pytest

from backend.models.enums import DietPreference, FeedingType, Sex
from backend.schemas.tools import FeedingEntry, GapDetectionRequest
from backend.tools.nutrient_gaps import detect_nutrient_gaps
from tests.fixtures.fake_llm import RecordingChatModel

AS_OF = date(2026, 8, 27)


def cereal_day(days_ago: int, grams: float) -> FeedingEntry:
    day = AS_OF - timedelta(days=days_ago)
    return FeedingEntry(
        fed_at=datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC),
        feeding_type=FeedingType.SOLID,
        food_id="infant_cereal_iron_fortified",
        quantity=grams,
        unit="g",
    )


def request(entries: list[FeedingEntry], **fields) -> GapDetectionRequest:
    base = dict(age_months=8, weight_kg=8.5, sex=Sex.FEMALE, entries=entries, as_of=AS_OF)
    return GapDetectionRequest(**{**base, **fields})


def audit_records(caplog) -> list[dict]:
    return [
        json.loads(r.getMessage().removeprefix("nutrient_gaps_audit "))
        for r in caplog.records
        if r.name == "backend.tools.audit" and r.getMessage().startswith("nutrient_gaps_audit ")
    ]


class TestDetection:
    async def test_doctors_note_prevents_a_false_deficit(self) -> None:
        # 100 g cereal = 400 kcal a day: 59% of the general 678 kcal (below), but 80% of a
        # 500 kcal limit (adequate). The note must be what we measure against.
        llm = RecordingChatModel(
            responses=['{"nutrient": "calories", "direction": "max", "value": 500, "unit": "kcal"}']
        )
        report = await detect_nutrient_gaps(
            request(
                [cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)],
                doctors_note="Limit to 500 kcal per day.",
            ),
            llm,
        )
        assert report.status == "ok" and report.confidence == "medium"
        calories = next(g for g in report.gaps if g.nutrient == "calories")
        assert calories.target == 500 and calories.ratio == 0.8 and calories.flag == "adequate"
        assert report.override is not None and report.override.conflict is True
        assert report.override.general_value == 678
        assert report.note_extraction is not None and report.note_extraction.status == "applied"

    async def test_same_intake_without_the_note_is_below(self) -> None:
        report = await detect_nutrient_gaps(
            request([cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)]), None
        )
        calories = next(g for g in report.gaps if g.nutrient == "calories")
        assert calories.target == 678 and calories.flag == "below"
        iron = next(g for g in report.gaps if g.nutrient == "iron")
        assert iron.flag == "above"  # 33 mg a day against 11 mg

    async def test_empty_log_is_insufficient_data(self) -> None:
        report = await detect_nutrient_gaps(request([]), None)
        assert report.status == "insufficient_data"
        assert report.gaps == [] and report.days_logged == 0 and report.as_of == AS_OF
        assert report.targets.calories.calories == 678
        assert report.override is not None and report.override.conflict is False

    async def test_reference_day_and_partial_days_excluded(self) -> None:
        unmeasured = FeedingEntry(
            fed_at=datetime(2026, 8, 25, 20, 0, tzinfo=UTC), feeding_type=FeedingType.BREASTMILK
        )
        report = await detect_nutrient_gaps(
            request([cereal_day(0, 100), cereal_day(1, 100), cereal_day(2, 100), unmeasured]), None
        )
        assert report.days_logged == 1 and report.partial_days == 1
        assert report.confidence == "low" and report.directional

    async def test_deterministic(self) -> None:
        entries = [cereal_day(1, 100), cereal_day(2, 120)]
        assert await detect_nutrient_gaps(request(entries), None) == await detect_nutrient_gaps(
            request(entries), None
        )


class TestAudit:
    async def test_audit_record_has_input_days_window_confidence_gaps_override(
        self, caplog
    ) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await detect_nutrient_gaps(
            request([cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)]), None
        )
        [record] = audit_records(caplog)
        assert record["event"] == "nutrient_gaps" and record["status"] == "ok"
        assert record["input"]["age_months"] == 8 and record["input"]["entries"] == 3
        assert record["input"]["timezone"] == "UTC" and record["as_of"] == "2026-08-27"
        assert record["days_logged"] == 3 and record["window_days"] == 3
        assert record["confidence"] == "medium" and record["partial_days"] == 0
        # Calcium joined the trackable set on day 9 (nutrient-gap-detection delta spec).
        assert {g["nutrient"] for g in record["gaps"]} == {"calories", "protein", "iron", "calcium"}
        assert all(g["target_source"] for g in record["gaps"])
        assert record["override"]["conflict"] is False

    async def test_insufficient_data_is_audited_too(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await detect_nutrient_gaps(request([]), None)
        [record] = audit_records(caplog)
        assert record["status"] == "insufficient_data" and record["gaps"] == []


class TestTrackability:
    """day-9 nutrient-gap-detection delta spec: the flagged set is the trackable subset."""

    async def test_calcium_joins_the_report_with_label_and_unit(self) -> None:
        report = await detect_nutrient_gaps(
            request([cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)]), None
        )
        calcium = next(g for g in report.gaps if g.nutrient == "calcium")
        # 7-12 months AI from nih-dri-micronutrients.md; the label rides the payload
        # (design Decision 10) so the renderer never needs a local name map.
        assert calcium.target == 260 and calcium.label == "Calcium" and calcium.unit == "mg"
        assert calcium.flag == "above"  # ~667 mg/day of fortified cereal against 260
        # The original three are still reported with their previously asserted figures.
        assert next(g for g in report.gaps if g.nutrient == "calories").target == 678
        assert next(g for g in report.gaps if g.nutrient == "iron").target == 11.0

    @pytest.mark.parametrize(
        ("days", "confidence"), [(1, "low"), (3, "medium"), (8, "high")]
    )
    async def test_vitamin_d_is_never_flagged_at_any_confidence(
        self, days: int, confidence: str
    ) -> None:
        entries = [cereal_day(i, 100) for i in range(1, days + 1)]
        report = await detect_nutrient_gaps(request(entries), None)
        assert report.confidence == confidence
        assert "vitamin_d" not in {g.nutrient for g in report.gaps}
        # Displayed with its target, unscored, and carrying the parent-facing reason.
        vitamin_d = report.targets.require("vitamin_d")
        assert vitamin_d.tracked is False and vitamin_d.not_tracked_reason

    async def test_vegan_b12_is_absent_not_below(self) -> None:
        entries = [cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)]
        report = await detect_nutrient_gaps(
            request(entries, diet_preference=DietPreference.VEGAN), None
        )
        assert "vitamin_b12" not in {g.nutrient for g in report.gaps}
        b12 = report.targets.require("vitamin_b12")
        assert b12.tracked is False
        assert "supplement" in b12.display_note

    async def test_diet_edit_changes_trackability_and_nothing_else(self) -> None:
        entries = [cereal_day(1, 100), cereal_day(2, 100), cereal_day(3, 100)]
        vegetarian = await detect_nutrient_gaps(
            request(entries, diet_preference=DietPreference.VEGETARIAN), None
        )
        vegan = await detect_nutrient_gaps(
            request(entries, diet_preference=DietPreference.VEGAN), None
        )
        for report in (vegetarian, vegan):
            flagged = {g.nutrient for g in report.gaps}
            assert flagged == {r.nutrient for r in report.targets.tracked()}
            assert "vitamin_b12" not in flagged  # no loggable source yet for either diet
        shared = {g.nutrient for g in vegetarian.gaps} & {g.nutrient for g in vegan.gaps}
        for key in shared:
            before = next(g for g in vegetarian.gaps if g.nutrient == key)
            after = next(g for g in vegan.gaps if g.nutrient == key)
            assert (before.average, before.flag) == (after.average, after.flag), key
