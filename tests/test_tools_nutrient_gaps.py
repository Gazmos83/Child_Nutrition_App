"""detect_nutrient_gaps over a client-held log (change 2 task 2.3; nutrient-gap-detection spec)."""

import json
import logging
from datetime import UTC, date, datetime, timedelta

from backend.models.enums import FeedingType, Sex
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
        assert {g["nutrient"] for g in record["gaps"]} == {"calories", "protein", "iron"}
        assert all(g["target_source"] for g in record["gaps"])
        assert record["override"]["conflict"] is False

    async def test_insufficient_data_is_audited_too(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await detect_nutrient_gaps(request([]), None)
        [record] = audit_records(caplog)
        assert record["status"] == "insufficient_data" and record["gaps"] == []
