"""Feeding-log tools: ``log_feeding``, ``get_daily_nutrition``, ``get_remaining_targets``
(feeding-log spec; change 2 design Decisions 3, 4, 5, 10).

``log_feeding`` validates, normalises, and prices one entry and hands it back with an
identifier. It stores nothing: the log is client-held until the Day 6 ``feeding_log``
table ships, at which point this function gains a row write for the authenticated user's
child and nothing else changes.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel

from backend.nutrition.feeding import (
    NormalisedEntry,
    is_complete,
    local_date,
    normalise_entries,
    normalise_entry,
    sum_totals,
)
from backend.nutrition.foods import LoadedFoodTable, get_food_table
from backend.schemas.tools import (
    DailyNutritionInput,
    DailyNutritionResult,
    FeedingEntry,
    LoggedFeeding,
    RemainingNutrients,
    RemainingTargetsInput,
    RemainingTargetsResult,
)
from backend.tools.targets_resolution import resolve_targets


def _today(timezone: str) -> dt.date:
    return dt.datetime.now(ZoneInfo(timezone)).date()


def _logged(item: NormalisedEntry, table: LoadedFoodTable) -> LoggedFeeding:
    entry = item.entry
    if entry.id is None:
        entry = entry.model_copy(update={"id": str(uuid.uuid7())})
    return LoggedFeeding(
        entry=entry,
        food_id=item.food_id,
        food_name=item.food.name if item.food is not None else None,
        quantified=item.quantified,
        nutrients=item.nutrients,
        source=table.source_for(item.food) if item.food is not None else table.table.source,
    )


def log_feeding(entry: FeedingEntry, table: LoadedFoodTable | None = None) -> LoggedFeeding:
    """Validate against the table, price the feed, assign an id. No persistence (Day 6)."""
    table = table or get_food_table()
    return _logged(normalise_entry(entry, table), table)


def get_daily_nutrition(
    params: DailyNutritionInput, table: LoadedFoodTable | None = None
) -> DailyNutritionResult:
    """Totals for one local day; entries from other days are left out."""
    table = table or get_food_table()
    day = params.date or _today(params.timezone)
    items = [
        item
        for item in normalise_entries(params.entries, table)
        if local_date(item.entry.fed_at, params.timezone) == day
    ]
    return DailyNutritionResult(
        date=day,
        timezone=params.timezone,
        entries=[_logged(item, table) for item in items],
        totals=sum_totals(item.nutrients for item in items),
        complete=is_complete(items),
        unquantified=sum(1 for item in items if not item.quantified),
        source=table.table.source,
    )


async def get_remaining_targets(
    params: RemainingTargetsInput,
    chat_model: BaseChatModel | None,
    table: LoadedFoodTable | None = None,
) -> RemainingTargetsResult:
    """The child's targets (doctor's note honoured) minus the day's intake, floored at zero."""
    table = table or get_food_table()
    targets, extraction, override = await resolve_targets(params, chat_model)
    daily = get_daily_nutrition(
        DailyNutritionInput(entries=params.entries, timezone=params.timezone, date=params.date),
        table,
    )
    intake = daily.totals
    remaining = RemainingNutrients(
        calories=round(max(0.0, targets.calories.calories - intake.calories), 1),
        protein_g=round(max(0.0, targets.protein.protein_g - intake.protein_g), 1),
        iron_mg=round(max(0.0, targets.iron.iron_mg - intake.iron_mg), 1),
    )
    return RemainingTargetsResult(
        date=daily.date,
        timezone=params.timezone,
        targets=targets,
        intake=intake,
        remaining=remaining,
        note_extraction=extraction,
        override=override,
        source=table.table.source,
    )
