"""Diet-preference exclusions (design.md Decision 6).

A household's dietary pattern, kept apart from the safety filter on purpose: preference is
a choice, safety is not, and the safety filter's rule set must stay exactly the hard-rule-4
checks. Milk feeds (breast milk, infant formula) are never excluded by preference -- they
are the only food under 6 months and the required drink under 12.
"""

from collections.abc import Iterable

from backend.models.enums import DietPreference
from backend.nutrition.foods import FoodCategory, FoodItem

_ANIMAL_FLESH = frozenset(
    {FoodCategory.MEAT, FoodCategory.POULTRY, FoodCategory.FISH, FoodCategory.SHELLFISH}
)

EXCLUDED_CATEGORIES: dict[DietPreference, frozenset[FoodCategory]] = {
    DietPreference.OMNIVORE: frozenset(),
    DietPreference.PESCATARIAN: frozenset({FoodCategory.MEAT, FoodCategory.POULTRY}),
    DietPreference.VEGETARIAN: _ANIMAL_FLESH,
    DietPreference.VEGAN: _ANIMAL_FLESH | {FoodCategory.DAIRY, FoodCategory.EGG},
}


def is_allowed(food: FoodItem, preference: DietPreference) -> bool:
    if food.category is FoodCategory.MILK_FEED:
        return True
    if food.category in EXCLUDED_CATEGORIES[preference]:
        return False
    # Honey is an animal product.
    return not (preference is DietPreference.VEGAN and food.contains_honey)


def filter_by_diet(
    foods: Iterable[FoodItem], preference: DietPreference
) -> tuple[list[FoodItem], list[FoodItem]]:
    """Partition into (allowed, excluded) for the preference. Order is preserved."""
    allowed: list[FoodItem] = []
    excluded: list[FoodItem] = []
    for food in foods:
        (allowed if is_allowed(food, preference) else excluded).append(food)
    return allowed, excluded
