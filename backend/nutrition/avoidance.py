"""Foods and food groups a note row says to avoid, resolved and applied in code
(child-notes-restrictions design Decision 5).

The language model hands over a plain phrase; everything here is deterministic: a food
category (by name, plural, or a fixed alias) wins first, else every table food the phrase
names under the table's own whole-word rule. An ambiguous phrase excludes every candidate
-- for an avoidance, under-excluding is the dangerous failure and over-excluding is visible
under "Left out, and why". Milk feeds are never excluded: whether a child has breast milk
or formula is the pediatrician's call, and the planner anchors every plan on one. No model
call, no LangChain import (Day 4 Decision 1 invariant).
"""

from collections.abc import Callable, Iterable

from backend.chat import copy
from backend.models.enums import NoteKind
from backend.nutrition.foods import FoodCategory, FoodItem, LoadedFoodTable
from backend.schemas.tools import Avoidance, ExtractedAvoidance


def _aliases() -> dict[str, FoodCategory]:
    table: dict[str, FoodCategory] = {}
    for category in FoodCategory:
        if category is FoodCategory.MILK_FEED:
            continue
        spaced = category.value.replace("_", " ")
        for form in (category.value, spaced, spaced + "s", spaced + "es"):
            table[form] = category
    table.update(
        {
            "dairy products": FoodCategory.DAIRY,
            "milk products": FoodCategory.DAIRY,
            "nuts": FoodCategory.NUT_SEED,
            "seeds": FoodCategory.NUT_SEED,
            "nuts and seeds": FoodCategory.NUT_SEED,
            "tree nuts": FoodCategory.NUT_SEED,
            "fats": FoodCategory.FAT_OIL,
            "oils": FoodCategory.FAT_OIL,
            "fats and oils": FoodCategory.FAT_OIL,
            "sweets": FoodCategory.SWEETENER,
            "sugar": FoodCategory.SWEETENER,
            "sugars": FoodCategory.SWEETENER,
            "sweeteners": FoodCategory.SWEETENER,
            "added sugar": FoodCategory.SWEETENER,
            "legumes": FoodCategory.LEGUME,
            "beans": FoodCategory.LEGUME,
            "pulses": FoodCategory.LEGUME,
            "eggs": FoodCategory.EGG,
            "grains": FoodCategory.GRAIN,
            "seafood": FoodCategory.FISH,
            "vegetables": FoodCategory.VEGETABLE,
            "fruits": FoodCategory.FRUIT,
        }
    )
    return table


CATEGORY_ALIASES: dict[str, FoodCategory] = _aliases()


def _normalise(phrase: str) -> str:
    return " ".join(phrase.lower().replace("-", " ").split())


def resolve_avoidance(
    item: ExtractedAvoidance, kind: NoteKind, table: LoadedFoodTable
) -> Avoidance:
    """A category, else every matching food (minus milk feeds), else not applied."""
    phrase = _normalise(item.phrase)
    category = CATEGORY_ALIASES.get(phrase)
    if category is not None:
        food_ids = [food.id for food in table.foods if food.category is category]
        return Avoidance(
            note_index=item.note_index,
            kind=kind,
            phrase=item.phrase,
            category=category.value,
            food_ids=food_ids,
            applied=True,
            detail=copy.avoidance_applied(item.phrase, len(food_ids)),
        )
    matched = table.matches(item.phrase)
    foods = [food for food in matched if food.category is not FoodCategory.MILK_FEED]
    if foods:
        detail = copy.avoidance_applied(item.phrase, len(foods))
        if len(foods) < len(matched):
            detail = f"{detail}; {copy.NOTE_MILK_FEED}"  # "milk" also named a milk feed
        return Avoidance(
            note_index=item.note_index,
            kind=kind,
            phrase=item.phrase,
            food_ids=[food.id for food in foods],
            applied=True,
            detail=detail,
        )
    detail = copy.NOTE_MILK_FEED if matched else copy.note_no_match(item.phrase)
    return Avoidance(
        note_index=item.note_index, kind=kind, phrase=item.phrase, applied=False, detail=detail
    )


def filter_by_avoidances(
    foods: Iterable[FoodItem],
    avoidances: Iterable[Avoidance],
    reason_for: Callable[[Avoidance], str],
) -> tuple[list[FoodItem], list[tuple[FoodItem, list[str]]]]:
    """Partition ``foods`` into kept and (excluded, reasons); order preserved, a food hit by
    several rows collects every reason (mirrors ``diet.filter_by_diet``)."""
    reasons_by_food: dict[str, list[str]] = {}
    for avoidance in avoidances:
        if not avoidance.applied:
            continue
        for food_id in avoidance.food_ids:
            reasons_by_food.setdefault(food_id, []).append(reason_for(avoidance))
    kept: list[FoodItem] = []
    excluded: list[tuple[FoodItem, list[str]]] = []
    for food in foods:
        reasons = reasons_by_food.get(food.id)
        if reasons:
            excluded.append((food, reasons))
        else:
            kept.append(food)
    return kept, excluded
