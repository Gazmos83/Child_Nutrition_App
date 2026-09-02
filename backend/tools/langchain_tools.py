"""LangChain ``StructuredTool`` wrappers for Day 5's router (design.md Decision 10).

Each tool's ``args_schema`` is the Pydantic input model, so the model's arguments are
validated before any function runs (hard rule 7). The pure tools are synchronous;
``generate_meal_plan``, ``get_remaining_targets``, and ``detect_nutrient_gaps`` are
coroutine-only because target resolution may await the chat model for a doctor's note.
Log-backed arguments (``entries``, ``logged_today``, ``timezone``) are filled from the
request by ``resolve_context``, never typed out by the model (change 2 design Decision 9).
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool

from backend.schemas.tools import (
    BmiInput,
    CalorieTargetInput,
    DailyNutritionInput,
    FeedingEntry,
    FoodLookupInput,
    GapDetectionRequest,
    GrowthAssessmentInput,
    MealNutritionInput,
    MealPlanRequest,
    ProteinTargetInput,
    RemainingTargetsInput,
)
from backend.tools import nutrient_tools
from backend.tools.feeding_log import get_daily_nutrition, get_remaining_targets, log_feeding
from backend.tools.meal_plan import generate_meal_plan
from backend.tools.nutrient_gaps import detect_nutrient_gaps


def build_tools(chat_model: BaseChatModel | None) -> list[StructuredTool]:
    """The six Day 4 tools plus the four feeding-log tools. ``chat_model`` is used only for
    doctor's-note extraction."""

    def bmi(**kwargs):
        return nutrient_tools.calculate_bmi(BmiInput(**kwargs))

    def growth(**kwargs):
        return nutrient_tools.assess_growth(GrowthAssessmentInput(**kwargs))

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

    def feeding(**kwargs):
        return log_feeding(FeedingEntry(**kwargs))

    def daily_nutrition(**kwargs):
        return get_daily_nutrition(DailyNutritionInput(**kwargs))

    async def remaining_targets(**kwargs):
        return await get_remaining_targets(RemainingTargetsInput(**kwargs), chat_model)

    async def nutrient_gaps(**kwargs):
        return await detect_nutrient_gaps(GapDetectionRequest(**kwargs), chat_model)

    return [
        StructuredTool.from_function(
            func=bmi,
            name="calculate_bmi",
            description=(
                "Compute a child's BMI from weight in kilograms and height in centimetres. "
                "Returns the BMI value only; for the growth-chart percentile use "
                "assess_growth."
            ),
            args_schema=BmiInput,
        ),
        StructuredTool.from_function(
            func=growth,
            name="assess_growth",
            description=(
                "Place a child on the WHO growth chart: BMI-for-age, weight-for-age, "
                "length/height-for-age, and weight-for-length/height as z-scores and "
                "percentiles with WHO reference values and cut-off bands. Use for BMI, "
                "percentile, or whether a child's weight or length is normal for their "
                "age. Needs age in months, sex, and weight; length/height is optional -- "
                "without it weight-for-age is still assessed."
            ),
            args_schema=GrowthAssessmentInput,
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
                "Look up one food in the curated infant/toddler food table by identifier or "
                "plain name -- food_id is the food only, never an amount or a question. "
                "Returns per-serving calories, protein, fat, carbohydrate, iron, calcium, "
                "allergens, choking-hazard/honey/unpasteurised flags, minimum age in months, "
                "and source. Pass quantity and unit (g or ml) when the parent names an "
                "amount; the result then also carries nutrients_for_quantity for exactly "
                "that amount. An unknown or ambiguous name fails with the closest matches."
            ),
            args_schema=FoodLookupInput,
        ),
        StructuredTool.from_function(
            func=meal_nutrition,
            name="calculate_meal_nutrition",
            description=(
                "Sum the nutrients of a meal from a list of foods (identifier or plain "
                "name), each with either servings (multiples of the table serving) or a "
                "quantity with unit (g or ml) as the parent said it. Unknown foods are "
                "reported in 'missing', never silently dropped."
            ),
            args_schema=MealNutritionInput,
        ),
        StructuredTool.from_function(
            coroutine=meal_plan,
            name="generate_meal_plan",
            description=(
                "Generate a one-day meal plan for a child from age in months, weight, sex, "
                "diet preference, recorded allergies, optional height (required from 36 "
                "months) and the doctor's-note and preference rows. Foods a row names are "
                "left out and listed with the reason; a doctor's row can also change a "
                "target. Applies the infant-safety filter and reports targets, totals, "
                "exclusions, overrides, what each row did, and a not-medical-advice "
                "disclaimer. When the parent has logged feeds, today's "
                "intake is subtracted so the plan covers the rest of the day, and a "
                "nutrient-gap report steers which foods are favoured."
            ),
            args_schema=MealPlanRequest,
        ),
        StructuredTool.from_function(
            func=feeding,
            name="log_feeding",
            description=(
                "Record one feed the child actually had: time, type (breastmilk, formula, "
                "solid, water), food from the table for solids, quantity and unit. Returns "
                "the entry with an id and its table-derived nutrients. Breast milk may be "
                "logged without a quantity. Nothing is stored yet; the parent's browser keeps "
                "the log."
            ),
            args_schema=FeedingEntry,
        ),
        StructuredTool.from_function(
            func=daily_nutrition,
            name="get_daily_nutrition",
            description=(
                "Total nutrients the child has had on one local day from the feeding log "
                "(default: today). Use when the parent asks what the child has had so far."
            ),
            args_schema=DailyNutritionInput,
        ),
        StructuredTool.from_function(
            coroutine=remaining_targets,
            name="get_remaining_targets",
            description=(
                "The child's daily calorie, protein, and iron targets minus what the feeding "
                "log says was eaten on that day (default: today), floored at zero; a doctor's "
                "note is honoured. Use when the parent asks what is still needed today."
            ),
            args_schema=RemainingTargetsInput,
        ),
        StructuredTool.from_function(
            coroutine=nutrient_gaps,
            name="detect_nutrient_gaps",
            description=(
                "Compare logged intake over the last days with the child's targets: a "
                "rolling-window report per nutrient (below, adequate, above) whose confidence "
                "grows with the number of complete days logged. Use when the parent asks "
                "whether intake has been enough lately or whether anything has been falling "
                "short."
            ),
            args_schema=GapDetectionRequest,
        ),
    ]
