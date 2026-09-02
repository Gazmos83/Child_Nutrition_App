"""Feeding-log arithmetic (feeding-log spec; change 2 design Decisions 1, 3, 4).

Turns validated ``FeedingEntry`` shapes into table facts: which food a feed was, what it
contributed, and which local day it belongs to. Pure Python over the food table -- no
model, no database, no LangChain import (Day 4 Decision 1 invariant).
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from backend.models.enums import FeedingType
from backend.nutrition.foods import FoodCategory, FoodItem, LoadedFoodTable
from backend.schemas.tools import FeedingEntry, NutrientTotals

# Which table row a milk feed means when the entry does not say (design Decision 3).
MILK_FEED_DEFAULTS: dict[FeedingType, str] = {
    FeedingType.BREASTMILK: "breast_milk",
    FeedingType.FORMULA: "infant_formula_iron_fortified",
}

ZERO_TOTALS = NutrientTotals(
    calories=0, protein_g=0, fat_g=0, carbohydrate_g=0, iron_mg=0, calcium_mg=0
)


class FeedingEntryError(ValueError):
    """An entry that passed shape validation but contradicts the food table."""


class UnitMismatchError(FeedingEntryError):
    """An amount given in a unit the food is not measured in (food-lookup-quantities)."""

    def __init__(self, food: FoodItem, unit: str) -> None:
        super().__init__(f"{food.name} is measured in {food.serving_unit}, not {unit}")
        self.food_name = food.name
        self.expected_unit = food.serving_unit
        self.given_unit = unit


def check_unit(food: FoodItem, unit: str) -> None:
    """Raise ``UnitMismatchError`` unless ``unit`` is the food's table unit."""
    if unit != food.serving_unit:
        raise UnitMismatchError(food, unit)


@dataclass(frozen=True)
class NormalisedEntry:
    """An entry resolved against the table, with its nutrient contribution."""

    entry: FeedingEntry
    food: FoodItem | None
    nutrients: NutrientTotals

    @property
    def quantified(self) -> bool:
        return self.entry.quantity is not None

    @property
    def food_id(self) -> str | None:
        return self.food.id if self.food is not None else None


def entry_nutrients(food: FoodItem, quantity: float) -> NutrientTotals:
    """``quantity / serving_size × per-serving`` for each nutrient, two decimals."""
    factor = quantity / food.serving_size
    return NutrientTotals(
        calories=round(food.calories * factor, 2),
        protein_g=round(food.protein_g * factor, 2),
        fat_g=round(food.fat_g * factor, 2),
        carbohydrate_g=round(food.carbohydrate_g * factor, 2),
        iron_mg=round(food.iron_mg * factor, 2),
        calcium_mg=round(food.calcium_mg * factor, 2),
    )


def normalise_entry(entry: FeedingEntry, table: LoadedFoodTable) -> NormalisedEntry:
    """Resolve the food and price the entry, or raise.

    ``FoodNotFoundError`` for an unknown id (never a substitute); ``FeedingEntryError``
    when the unit does not match the food or a milk feed names a non-milk food. Water and
    an unmeasured breastfeed contribute zero nutrients.
    """
    kind = entry.feeding_type
    if kind is FeedingType.WATER:
        return NormalisedEntry(entry, None, ZERO_TOTALS)
    food_id = entry.food_id or MILK_FEED_DEFAULTS[kind]
    food = table.get(food_id)
    if kind in MILK_FEED_DEFAULTS and food.category is not FoodCategory.MILK_FEED:
        raise FeedingEntryError(f"{food.id} is not a milk feed; a {kind.value} entry must name one")
    check_unit(food, entry.unit)
    if entry.quantity is None:
        return NormalisedEntry(entry, food, ZERO_TOTALS)
    return NormalisedEntry(entry, food, entry_nutrients(food, entry.quantity))


def normalise_entries(
    entries: Iterable[FeedingEntry], table: LoadedFoodTable
) -> list[NormalisedEntry]:
    return [normalise_entry(e, table) for e in entries]


def local_date(fed_at: dt.datetime, timezone: str) -> dt.date:
    """The calendar day of ``fed_at`` in the parent's zone (design Decision 4)."""
    return fed_at.astimezone(ZoneInfo(timezone)).date()


def group_by_day(
    entries: Iterable[NormalisedEntry], timezone: str
) -> dict[dt.date, list[NormalisedEntry]]:
    by_day: dict[dt.date, list[NormalisedEntry]] = defaultdict(list)
    for item in entries:
        by_day[local_date(item.entry.fed_at, timezone)].append(item)
    return dict(sorted(by_day.items()))


def sum_totals(parts: Iterable[NutrientTotals]) -> NutrientTotals:
    """Sum, rounded to one decimal like ``calculate_meal_nutrition``."""
    acc = dict.fromkeys(NutrientTotals.model_fields, 0.0)
    for part in parts:
        for key in acc:
            acc[key] += getattr(part, key)
    return NutrientTotals(**{k: round(v, 1) for k, v in acc.items()})


@dataclass(frozen=True)
class DayTotals:
    """One local day's intake and whether it can enter a window."""

    date: dt.date
    totals: NutrientTotals
    entries: int
    unquantified: int

    @property
    def complete(self) -> bool:
        """At least one entry and no unmeasured feed (nutrient-gap-detection spec)."""
        return self.entries > 0 and self.unquantified == 0


def is_complete(entries: Iterable[NormalisedEntry]) -> bool:
    items = list(entries)
    return bool(items) and all(e.quantified for e in items)


def day_totals(date: dt.date, entries: Iterable[NormalisedEntry]) -> DayTotals:
    items = list(entries)
    return DayTotals(
        date=date,
        totals=sum_totals(e.nutrients for e in items),
        entries=len(items),
        unquantified=sum(1 for e in items if not e.quantified),
    )


def daily_totals(by_day: Mapping[dt.date, list[NormalisedEntry]]) -> dict[dt.date, DayTotals]:
    return {date: day_totals(date, items) for date, items in by_day.items()}
