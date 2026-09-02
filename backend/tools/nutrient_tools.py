"""The deterministic nutrient tools (deterministic-nutrient-tools spec).

Each takes a validated Pydantic input and reads only the DRI formulas or the food table.
No model call, no persistence. ``lookup_food`` and ``calculate_meal_nutrition`` accept a
``table`` so tests can inject a temporary one; production callers use the process-wide
table.
"""

from backend.nutrition import growth, targets
from backend.nutrition.feeding import check_unit, entry_nutrients
from backend.nutrition.foods import FoodItem, FoodNotFoundError, LoadedFoodTable, get_food_table
from backend.nutrition.growth import LoadedGrowthTable, get_growth_table
from backend.schemas.tools import (
    BmiInput,
    BmiResult,
    CalorieTargetInput,
    CalorieTargetResult,
    FoodLookupInput,
    GrowthAssessmentInput,
    GrowthAssessmentResult,
    MealItem,
    MealNutritionInput,
    MealNutritionResult,
    NutrientTotals,
    ProteinTargetInput,
    ProteinTargetResult,
)


def calculate_bmi(params: BmiInput) -> BmiResult:
    return targets.calculate_bmi(params)


def assess_growth(
    params: GrowthAssessmentInput, table: LoadedGrowthTable | None = None
) -> GrowthAssessmentResult:
    """The child on the WHO growth standards; indicators the inputs cannot support are
    reported as skipped, never as a failure."""
    return growth.assess_growth(params, table or get_growth_table())


def calculate_calorie_target(params: CalorieTargetInput) -> CalorieTargetResult:
    return targets.calculate_calorie_target(params)


def calculate_protein_target(params: ProteinTargetInput) -> ProteinTargetResult:
    return targets.calculate_protein_target(params)


class FoodRecord(FoodItem):
    """A food as returned to callers: the table row plus its resolved source and, when the
    parent named an amount, the nutrients for exactly that amount."""

    resolved_source: str
    requested_quantity: float | None = None
    requested_unit: str | None = None
    nutrients_for_quantity: NutrientTotals | None = None


def _for_quantity(food: FoodItem, quantity: float, unit: str | None) -> tuple[str, NutrientTotals]:
    """``quantity / serving_size × per-serving`` in the food's unit; a contradicting unit
    raises ``UnitMismatchError`` (food-lookup-quantities design Decisions 1 and 3)."""
    unit = unit or food.serving_unit
    check_unit(food, unit)
    return unit, entry_nutrients(food, quantity)


def lookup_food(params: FoodLookupInput, table: LoadedFoodTable | None = None) -> FoodRecord:
    """The food's nutrient and safety record, or ``FoodNotFoundError`` -- never a substitute."""
    table = table or get_food_table()
    food = table.resolve(params.food_id)
    record = FoodRecord(**food.model_dump(), resolved_source=table.source_for(food))
    if params.quantity is None:
        return record
    unit, nutrients = _for_quantity(food, params.quantity, params.unit)
    return record.model_copy(
        update={
            "requested_quantity": params.quantity,
            "requested_unit": unit,
            "nutrients_for_quantity": nutrients,
        }
    )


def calculate_meal_nutrition(
    params: MealNutritionInput, table: LoadedFoodTable | None = None
) -> MealNutritionResult:
    """Sum nutrients over items measured in servings or in an amount with unit. Unknown
    ids are reported in ``missing``; an amount in the wrong unit raises."""
    table = table or get_food_table()
    totals = dict.fromkeys(NutrientTotals.model_fields, 0.0)
    counted: list[MealItem] = []
    missing: list[str] = []
    for item in params.items:
        try:
            food = table.resolve(item.food_id)
        except FoodNotFoundError:
            missing.append(item.food_id)
            continue
        counted.append(item)
        if item.quantity is not None:
            _, part = _for_quantity(food, item.quantity, item.unit)
            for key in totals:
                totals[key] += getattr(part, key)
            continue
        servings = item.servings or 0.0
        totals["calories"] += food.calories * servings
        totals["protein_g"] += food.protein_g * servings
        totals["fat_g"] += food.fat_g * servings
        totals["carbohydrate_g"] += food.carbohydrate_g * servings
        totals["iron_mg"] += food.iron_mg * servings
        totals["calcium_mg"] += food.calcium_mg * servings
    return MealNutritionResult(
        totals=NutrientTotals(**{k: round(v, 1) for k, v in totals.items()}),
        counted=counted,
        missing=missing,
        source=table.table.source,
    )
