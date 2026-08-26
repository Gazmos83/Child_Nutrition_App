"""LangChain ``StructuredTool`` wrappers for Day 5's router (design.md Decision 10).

Each tool's ``args_schema`` is the Pydantic input model, so the model's arguments are
validated before any function runs (hard rule 7). The five pure tools are synchronous;
``generate_meal_plan`` is coroutine-only because note extraction awaits the chat model.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool

from backend.schemas.tools import (
    BmiInput,
    CalorieTargetInput,
    FoodLookupInput,
    MealNutritionInput,
    MealPlanRequest,
    ProteinTargetInput,
)
from backend.tools import nutrient_tools
from backend.tools.meal_plan import generate_meal_plan


def build_tools(chat_model: BaseChatModel | None) -> list[StructuredTool]:
    """The six Day 4 tools. ``chat_model`` is used only for doctor's-note extraction."""

    def bmi(**kwargs):
        return nutrient_tools.calculate_bmi(BmiInput(**kwargs))

    def calorie_target(**kwargs):
        return nutrient_tools.calculate_calorie_target(CalorieTargetInput(**kwargs))

    def protein_target(**kwargs):
        return nutrient_tools.calculate_protein_target(ProteinTargetInput(**kwargs))

    def food_lookup(**kwargs):
        return nutrient_tools.lookup_food(FoodLookupInput(**kwargs))

    def meal_nutrition(**kwargs):
        return nutrient_tools.calculate_meal_nutrition(MealNutritionInput(**kwargs))

    async def meal_plan(**kwargs):
        return await generate_meal_plan(MealPlanRequest(**kwargs), chat_model)

    return [
        StructuredTool.from_function(
            func=bmi,
            name="calculate_bmi",
            description=(
                "Compute a child's BMI from weight in kilograms and height in centimetres. "
                "Returns the BMI value only, not a growth-chart percentile."
            ),
            args_schema=BmiInput,
        ),
        StructuredTool.from_function(
            func=calorie_target,
            name="calculate_calorie_target",
            description=(
                "Daily calorie (energy) target for a child from age in months, weight in kg, "
                "sex, and -- from 36 months -- height in cm and activity level, using the "
                "DRI Estimated Energy Requirement equations."
            ),
            args_schema=CalorieTargetInput,
        ),
        StructuredTool.from_function(
            func=protein_target,
            name="calculate_protein_target",
            description=(
                "Daily protein target in grams for a child from age in months and weight in "
                "kg, using the DRI per-kilogram reference values."
            ),
            args_schema=ProteinTargetInput,
        ),
        StructuredTool.from_function(
            func=food_lookup,
            name="lookup_food",
            description=(
                "Look up a food by its identifier in the curated infant/toddler food table: "
                "per-serving calories, protein, fat, carbohydrate, iron, calcium, allergens, "
                "choking-hazard/honey/unpasteurised flags, minimum age in months, and source."
            ),
            args_schema=FoodLookupInput,
        ),
        StructuredTool.from_function(
            func=meal_nutrition,
            name="calculate_meal_nutrition",
            description=(
                "Sum the nutrients of a meal given a list of food identifiers and servings. "
                "Unknown identifiers are reported in 'missing', never silently dropped."
            ),
            args_schema=MealNutritionInput,
        ),
        StructuredTool.from_function(
            coroutine=meal_plan,
            name="generate_meal_plan",
            description=(
                "Generate a one-day meal plan for a child from age in months, weight, sex, "
                "diet preference, recorded allergies, optional height (required from 36 "
                "months) and optional doctor's note. Applies the infant-safety filter and "
                "reports targets, totals, exclusions, any doctor's-note override, and a "
                "not-medical-advice disclaimer."
            ),
            args_schema=MealPlanRequest,
        ),
    ]
