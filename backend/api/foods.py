"""``GET /api/foods`` -- the food table for the picker (feeding-log spec).

Reads the committed food-composition table only; no user data, no identity.
"""

from fastapi import APIRouter

from backend.nutrition.foods import get_food_table
from backend.schemas.tools import FoodSummary

router = APIRouter(tags=["foods"])


@router.get("/foods", response_model=list[FoodSummary], summary="List the foods a feed can name")
def list_foods() -> list[FoodSummary]:
    return [
        FoodSummary(
            id=food.id,
            name=food.name,
            category=food.category.value,
            serving_size=food.serving_size,
            serving_unit=food.serving_unit,
            min_age_months=food.min_age_months,
        )
        for food in get_food_table().foods
    ]
