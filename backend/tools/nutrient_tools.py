"""The deterministic nutrient tools (deterministic-nutrient-tools spec).

Each takes a validated Pydantic input and reads only the DRI formulas or the food table.
No model call, no persistence. ``lookup_food`` and ``calculate_meal_nutrition`` accept a
``table`` so tests can inject a temporary one; production callers use the process-wide
table.
"""

from backend.nutrition import growth, targets
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
    """A food as returned to callers: the table row plus its resolved source."""

    resolved_source: str


def lookup_food(params: FoodLookupInput, table: LoadedFoodTable | None = None) -> FoodRecord:
    """The food's nutrient and safety record, or ``FoodNotFoundError`` -- never a substitute."""
    table = table or get_food_table()
    food = table.resolve(params.food_id)
    return FoodRecord(**food.model_dump(), resolved_source=table.source_for(food))


def calculate_meal_nutrition(
    params: MealNutritionInput, table: LoadedFoodTable | None = None
) -> MealNutritionResult:
    """Sum nutrients over (food, servings). Unknown ids are reported in ``missing``."""
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
        totals["calories"] += food.calories * item.servings
        totals["protein_g"] += food.protein_g * item.servings
        totals["fat_g"] += food.fat_g * item.servings
        totals["carbohydrate_g"] += food.carbohydrate_g * item.servings
        totals["iron_mg"] += food.iron_mg * item.servings
        totals["calcium_mg"] += food.calcium_mg * item.servings
    return MealNutritionResult(
        totals=NutrientTotals(**{k: round(v, 1) for k, v in totals.items()}),
        counted=counted,
        missing=missing,
        source=table.table.source,
    )
