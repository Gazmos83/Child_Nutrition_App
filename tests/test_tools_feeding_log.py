"""log_feeding, get_daily_nutrition, get_remaining_targets (change 2 task 2.2; feeding-log spec)."""

from datetime import UTC, date, datetime

import pytest

from backend.models.enums import FeedingType, NoteKind, Sex
from backend.nutrition.foods import FoodNotFoundError
from backend.schemas.tools import (
    DailyNutritionInput,
    FeedingEntry,
    NoteRow,
    RemainingTargetsInput,
)
from backend.tools.feeding_log import get_daily_nutrition, get_remaining_targets, log_feeding
from tests.fixtures.fake_llm import RecordingChatModel

DAY = date(2026, 8, 27)


def at(hour: int, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


def formula(ml: float, hour: int = 9, day: date = DAY, **fields) -> FeedingEntry:
    return FeedingEntry(
        fed_at=at(hour, day), feeding_type=FeedingType.FORMULA, quantity=ml, **fields
    )


def cereal(grams: float, hour: int = 12, day: date = DAY) -> FeedingEntry:
    return FeedingEntry(
        fed_at=at(hour, day),
        feeding_type=FeedingType.SOLID,
        food_id="infant_cereal_iron_fortified",
        quantity=grams,
        unit="g",
    )


class TestLogFeeding:
    def test_returns_id_food_and_nutrients_without_storing(self) -> None:
        logged = log_feeding(formula(150))
        assert logged.entry.id and len(logged.entry.id) == 36
        assert logged.food_id == "infant_formula_iron_fortified"
        assert logged.food_name.startswith("Infant formula")
        assert logged.quantified
        assert logged.nutrients.calories == 100.5
        assert logged.nutrients.protein_g == 2.1
        assert logged.nutrients.iron_mg == 1.8
        assert "formula" in logged.source.lower()  # the entry-level source, not the table default

    def test_keeps_a_client_supplied_id(self) -> None:
        logged = log_feeding(formula(150, id="client-1"))
        assert logged.entry.id == "client-1"

    def test_two_logs_get_distinct_ids(self) -> None:
        assert log_feeding(formula(100)).entry.id != log_feeding(formula(100)).entry.id

    def test_unmeasured_breastfeed_is_unquantified_with_zero_nutrients(self) -> None:
        logged = log_feeding(FeedingEntry(fed_at=at(7), feeding_type=FeedingType.BREASTMILK))
        assert not logged.quantified and logged.food_id == "breast_milk"
        assert logged.nutrients.calories == 0

    def test_water_has_no_food(self) -> None:
        logged = log_feeding(
            FeedingEntry(fed_at=at(7), feeding_type=FeedingType.WATER, quantity=50)
        )
        assert logged.food_id is None and logged.food_name is None
        assert logged.nutrients.calories == 0

    def test_unknown_food_raises(self) -> None:
        with pytest.raises(FoodNotFoundError, match="dragonfruit"):
            log_feeding(
                FeedingEntry(
                    fed_at=at(7),
                    feeding_type=FeedingType.SOLID,
                    food_id="dragonfruit",
                    quantity=30,
                    unit="g",
                )
            )


class TestDailyNutrition:
    def test_only_the_requested_local_day_counts(self) -> None:
        yesterday = date(2026, 8, 26)
        result = get_daily_nutrition(
            DailyNutritionInput(
                entries=[
                    formula(150),
                    formula(150, hour=15),
                    cereal(15),
                    formula(200, day=yesterday),
                ],
                timezone="UTC",
                date=DAY,
            )
        )
        assert result.date == DAY
        assert len(result.entries) == 3
        assert result.totals.calories == 261.0
        assert result.totals.protein_g == 5.7
        assert result.totals.iron_mg == 8.6
        assert result.complete and result.unquantified == 0

    def test_timezone_moves_a_late_feed_to_the_next_day(self) -> None:
        late = FeedingEntry(fed_at=at(23), feeding_type=FeedingType.FORMULA, quantity=100)
        utc = get_daily_nutrition(DailyNutritionInput(entries=[late], timezone="UTC", date=DAY))
        tokyo = get_daily_nutrition(
            DailyNutritionInput(entries=[late], timezone="Asia/Tokyo", date=date(2026, 8, 28))
        )
        assert len(utc.entries) == 1 and len(tokyo.entries) == 1

    def test_unmeasured_feed_marks_day_incomplete(self) -> None:
        result = get_daily_nutrition(
            DailyNutritionInput(
                entries=[
                    formula(150),
                    FeedingEntry(fed_at=at(20), feeding_type=FeedingType.BREASTMILK),
                ],
                date=DAY,
            )
        )
        assert not result.complete and result.unquantified == 1
        assert result.totals.calories == 100.5

    def test_empty_day(self) -> None:
        result = get_daily_nutrition(DailyNutritionInput(date=DAY))
        assert result.entries == [] and result.totals.calories == 0 and not result.complete


class TestRemainingTargets:
    async def test_note_wins_and_remaining_subtracts_intake(self) -> None:
        llm = RecordingChatModel(
            responses=[
                '{"rows": [{"row": 1, "target": {"nutrient": "calories", "direction": "max", '
                '"value": 650, "unit": "kcal"}, "avoid": []}]}'
            ]
        )
        result = await get_remaining_targets(
            RemainingTargetsInput(
                age_months=8,
                weight_kg=8.5,
                sex=Sex.FEMALE,
                notes=[NoteRow(kind=NoteKind.DOCTOR, text="Limit to 650 kcal per day.")],
                entries=[cereal(75)],  # 5 servings x 60 kcal = 300 kcal
                date=DAY,
            ),
            llm,
        )
        assert result.overrides[0].conflict is True
        assert result.overrides[0].general_value == 678
        assert result.targets.calories.calories == 650
        assert result.intake.calories == 300.0
        assert result.remaining.calories == 350.0
        assert result.remaining.protein_g == round(result.targets.protein.protein_g - 7.5, 1)

    async def test_remaining_floors_at_zero(self) -> None:
        result = await get_remaining_targets(
            RemainingTargetsInput(
                age_months=8, weight_kg=8.5, sex=Sex.FEMALE, entries=[cereal(300)], date=DAY
            ),
            None,
        )
        assert result.intake.calories == 1200.0
        assert result.remaining.calories == 0.0
        assert result.remaining.iron_mg == 0.0  # 100 mg logged against an 11 mg target
        assert result.overrides == []

    async def test_no_entries_means_remaining_equals_targets(self) -> None:
        result = await get_remaining_targets(
            RemainingTargetsInput(age_months=8, weight_kg=8.5, sex=Sex.FEMALE, date=DAY), None
        )
        assert result.remaining.calories == float(result.targets.calories.calories)
        assert result.remaining.protein_g == result.targets.protein.protein_g
