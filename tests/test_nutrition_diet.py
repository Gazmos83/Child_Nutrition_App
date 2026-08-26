"""Diet-preference exclusions (task 3.2; meal-plan-generation spec: diet respected)."""

from backend.models.enums import DietPreference
from backend.nutrition.diet import EXCLUDED_CATEGORIES, filter_by_diet, is_allowed
from backend.nutrition.foods import FoodCategory, FoodItem


def food(food_id: str, category: FoodCategory, **overrides) -> FoodItem:
    base = dict(
        id=food_id,
        name=food_id,
        category=category,
        serving_size=50,
        serving_unit="g",
        calories=40,
        protein_g=1,
        fat_g=0.1,
        carbohydrate_g=9,
        iron_mg=0.2,
        calcium_mg=5,
        allergens=frozenset(),
        choking_hazard=False,
        contains_honey=False,
        commonly_unpasteurized=False,
        min_age_months=6,
    )
    return FoodItem(**{**base, **overrides})


FOODS = [
    food("breast_milk", FoodCategory.MILK_FEED, min_age_months=0),
    food("formula", FoodCategory.MILK_FEED, min_age_months=0),
    food("yogurt", FoodCategory.DAIRY),
    food("egg", FoodCategory.EGG),
    food("beef", FoodCategory.MEAT),
    food("chicken", FoodCategory.POULTRY),
    food("salmon", FoodCategory.FISH),
    food("shrimp", FoodCategory.SHELLFISH),
    food("lentils", FoodCategory.LEGUME),
    food("oats", FoodCategory.GRAIN),
    food("carrot", FoodCategory.VEGETABLE),
    food("banana", FoodCategory.FRUIT),
    food("tahini", FoodCategory.NUT_SEED),
    food("oil", FoodCategory.FAT_OIL),
    food("honey", FoodCategory.SWEETENER, contains_honey=True, min_age_months=12),
]
PLANT = {"lentils", "oats", "carrot", "banana", "tahini", "oil"}
MILK_FEEDS = {"breast_milk", "formula"}


def allowed_ids(preference: DietPreference) -> set[str]:
    allowed, _ = filter_by_diet(FOODS, preference)
    return {f.id for f in allowed}


def test_omnivore_excludes_nothing() -> None:
    assert allowed_ids(DietPreference.OMNIVORE) == {f.id for f in FOODS}
    assert EXCLUDED_CATEGORIES[DietPreference.OMNIVORE] == frozenset()


def test_pescatarian_keeps_fish_drops_meat_and_poultry() -> None:
    ids = allowed_ids(DietPreference.PESCATARIAN)
    assert {"salmon", "shrimp", "egg", "yogurt", "honey"} <= ids
    assert {"beef", "chicken"}.isdisjoint(ids)


def test_vegetarian_keeps_egg_and_dairy_drops_flesh() -> None:
    ids = allowed_ids(DietPreference.VEGETARIAN)
    assert {"egg", "yogurt", "honey"} <= ids
    assert {"beef", "chicken", "salmon", "shrimp"}.isdisjoint(ids)


def test_vegan_keeps_only_plants_and_milk_feeds() -> None:
    assert allowed_ids(DietPreference.VEGAN) == PLANT | MILK_FEEDS


def test_milk_feeds_never_excluded() -> None:
    for preference in DietPreference:
        assert allowed_ids(preference) >= MILK_FEEDS, preference


def test_vegan_excludes_honey_even_in_a_plant_category() -> None:
    honey_granola = food("honey_granola", FoodCategory.GRAIN, contains_honey=True)
    assert not is_allowed(honey_granola, DietPreference.VEGAN)
    assert is_allowed(honey_granola, DietPreference.VEGETARIAN)


def test_partition_is_complete_and_ordered() -> None:
    allowed, excluded = filter_by_diet(FOODS, DietPreference.VEGAN)
    assert len(allowed) + len(excluded) == len(FOODS)
    assert [f.id for f in allowed] == [f.id for f in FOODS if f.id in PLANT | MILK_FEEDS]
