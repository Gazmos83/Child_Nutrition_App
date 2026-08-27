"""Feeding entries become table nutrients and local days (change 2 task 1.3; feeding-log spec)."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.models.enums import FeedingType
from backend.nutrition.feeding import (
    FeedingEntryError,
    daily_totals,
    group_by_day,
    is_complete,
    local_date,
    normalise_entries,
    normalise_entry,
    sum_totals,
)
from backend.nutrition.foods import FoodNotFoundError, get_food_table
from backend.schemas.tools import FeedingEntry

AT = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)


def entry(feeding_type: FeedingType, **fields) -> FeedingEntry:
    return FeedingEntry(fed_at=AT, feeding_type=feeding_type, **fields)


@pytest.fixture(scope="module")
def table():
    return get_food_table()


class TestNormalise:
    def test_formula_volume_converted(self, table) -> None:
        item = normalise_entry(entry(FeedingType.FORMULA, quantity=150), table)
        assert item.food_id == "infant_formula_iron_fortified"
        assert item.quantified
        assert item.nutrients.calories == 100.5
        assert item.nutrients.protein_g == 2.1
        assert item.nutrients.iron_mg == 1.8

    def test_breastmilk_defaults_to_breast_milk(self, table) -> None:
        item = normalise_entry(entry(FeedingType.BREASTMILK, quantity=120), table)
        assert item.food_id == "breast_milk"
        assert item.nutrients.calories == 84.0

    def test_unquantified_breastmilk_contributes_nothing(self, table) -> None:
        item = normalise_entry(entry(FeedingType.BREASTMILK), table)
        assert not item.quantified
        assert item.food_id == "breast_milk"
        assert item.nutrients.calories == 0 and item.nutrients.iron_mg == 0

    def test_water_has_no_food_and_no_nutrients(self, table) -> None:
        item = normalise_entry(entry(FeedingType.WATER, quantity=60), table)
        assert item.food is None and item.food_id is None
        assert item.nutrients.calories == 0

    def test_solid_scaled_by_serving(self, table) -> None:
        item = normalise_entry(
            entry(FeedingType.SOLID, food_id="infant_cereal_iron_fortified", quantity=30, unit="g"),
            table,
        )
        assert item.nutrients.calories == 120.0 and item.nutrients.iron_mg == 10.0

    def test_unknown_solid_raises_food_not_found(self, table) -> None:
        with pytest.raises(FoodNotFoundError, match="dragonfruit"):
            normalise_entry(
                entry(FeedingType.SOLID, food_id="dragonfruit", quantity=30, unit="g"), table
            )

    def test_solid_unit_must_match_the_table(self, table) -> None:
        with pytest.raises(FeedingEntryError, match="measured in g, not ml"):
            normalise_entry(entry(FeedingType.SOLID, food_id="avocado", quantity=30), table)

    def test_formula_override_must_be_a_milk_feed(self, table) -> None:
        with pytest.raises(FeedingEntryError, match="not a milk feed"):
            normalise_entry(
                entry(FeedingType.FORMULA, food_id="whole_cows_milk", quantity=100), table
            )
        with pytest.raises(FeedingEntryError, match="not a milk feed"):
            normalise_entry(entry(FeedingType.FORMULA, food_id="avocado", quantity=100), table)

    def test_formula_in_grams_rejected_at_the_schema(self) -> None:
        with pytest.raises(ValueError, match="formula is measured in ml"):
            entry(FeedingType.FORMULA, quantity=150, unit="g")


class TestDays:
    def test_late_utc_feed_lands_on_next_day_in_tokyo(self) -> None:
        late = datetime(2026, 8, 27, 23, 30, tzinfo=UTC)
        assert local_date(late, "UTC") == date(2026, 8, 27)
        assert local_date(late, "Asia/Tokyo") == date(2026, 8, 28)

    def test_group_by_day_uses_the_local_zone(self, table) -> None:
        items = normalise_entries(
            [
                FeedingEntry(
                    fed_at=datetime(2026, 8, 27, 23, 30, tzinfo=UTC),
                    feeding_type=FeedingType.FORMULA,
                    quantity=100,
                ),
                FeedingEntry(
                    fed_at=datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
                    feeding_type=FeedingType.FORMULA,
                    quantity=100,
                ),
            ],
            table,
        )
        assert set(group_by_day(items, "UTC")) == {date(2026, 8, 27)}
        assert set(group_by_day(items, "Asia/Tokyo")) == {date(2026, 8, 27), date(2026, 8, 28)}

    def test_unquantified_breastmilk_marks_the_day_incomplete(self, table) -> None:
        items = normalise_entries(
            [entry(FeedingType.FORMULA, quantity=150), entry(FeedingType.BREASTMILK)], table
        )
        assert not is_complete(items)
        [day] = daily_totals(group_by_day(items, "UTC")).values()
        assert day.entries == 2 and day.unquantified == 1 and not day.complete
        assert day.totals.calories == 100.5  # the measured feed still counts toward totals

    def test_quantified_day_is_complete_and_summed(self, table) -> None:
        items = normalise_entries(
            [
                entry(FeedingType.FORMULA, quantity=150),
                entry(FeedingType.FORMULA, quantity=150),
                entry(
                    FeedingType.SOLID, food_id="infant_cereal_iron_fortified", quantity=15, unit="g"
                ),
            ],
            table,
        )
        [day] = daily_totals(group_by_day(items, "UTC")).values()
        assert day.complete
        assert day.totals.calories == 261.0
        assert day.totals.protein_g == 5.7
        assert day.totals.iron_mg == 8.6

    def test_empty_day_is_not_complete(self) -> None:
        assert not is_complete([])
        assert sum_totals([]).calories == 0


def test_nutrition_package_has_no_langchain_import() -> None:
    package = Path("backend") / "nutrition"
    offenders = [p for p in package.glob("*.py") if "langchain" in p.read_text(encoding="utf-8")]
    assert offenders == []
