"""The hard-coded infant-safety filter (hard rule 4; design.md Decision 7).

Pure Python with no dependency on the RAG pipeline or the language model. The thresholds
are module constants and the functions take no flag, setting, or parameter that disables
a rule: there is nothing a prompt or a tool call could pass to weaken it. The meal planner
runs ``filter_foods`` before composing and ``assert_plan_safe`` on its own output.

Rules (sources in the knowledge base):
- no honey under 12 months (CDC infant botulism guidance)
- no recognized choking hazard under 48 months (AAP Prevention of Choking, 2010)
- no commonly-unpasteurized product at any age (CDC food safety for children under 5)
- no food containing an allergen recorded against the child
- no food below its own minimum age (e.g. no solids under 6 months)
"""

from collections.abc import Iterable
from dataclasses import dataclass

from backend.models.enums import Allergen
from backend.nutrition.foods import FoodItem

HONEY_MIN_AGE_MONTHS = 12
CHOKING_HAZARD_MIN_AGE_MONTHS = 48


@dataclass(frozen=True)
class SafetyViolation:
    rule: str
    detail: str


@dataclass(frozen=True)
class Exclusion:
    food: FoodItem
    violations: tuple[SafetyViolation, ...]

    @property
    def reasons(self) -> list[str]:
        return [v.detail for v in self.violations]


class UnsafePlanError(RuntimeError):
    """A composed plan contained a food the filter forbids. Indicates a planner bug."""


def check_food(
    food: FoodItem, age_months: int, allergens: Iterable[Allergen]
) -> list[SafetyViolation]:
    """Every rule the food violates for this child. Empty means safe."""
    child_allergens = frozenset(allergens)
    violations: list[SafetyViolation] = []

    if food.contains_honey and age_months < HONEY_MIN_AGE_MONTHS:
        violations.append(
            SafetyViolation(
                "no_honey_under_12_months",
                f"contains honey; not safe under {HONEY_MIN_AGE_MONTHS} months (infant botulism)",
            )
        )
    if food.choking_hazard and age_months < CHOKING_HAZARD_MIN_AGE_MONTHS:
        violations.append(
            SafetyViolation(
                "no_choking_hazard_under_4_years",
                "recognized choking hazard for children under "
                f"{CHOKING_HAZARD_MIN_AGE_MONTHS} months",
            )
        )
    if food.commonly_unpasteurized:
        violations.append(
            SafetyViolation(
                "no_unpasteurized_products", "commonly served unpasteurized; not safe at any age"
            )
        )
    shared = sorted(a.value for a in food.allergens & child_allergens)
    if shared:
        violations.append(
            SafetyViolation(
                "no_recorded_allergen", f"contains recorded allergen: {', '.join(shared)}"
            )
        )
    if age_months < food.min_age_months:
        violations.append(
            SafetyViolation(
                "below_minimum_age",
                f"not introduced before {food.min_age_months} months",
            )
        )
    return violations


def filter_foods(
    foods: Iterable[FoodItem], age_months: int, allergens: Iterable[Allergen]
) -> tuple[list[FoodItem], list[Exclusion]]:
    """Partition candidates into (safe, excluded-with-reasons). Order is preserved."""
    child_allergens = frozenset(allergens)
    safe: list[FoodItem] = []
    excluded: list[Exclusion] = []
    for food in foods:
        violations = check_food(food, age_months, child_allergens)
        if violations:
            excluded.append(Exclusion(food, tuple(violations)))
        else:
            safe.append(food)
    return safe, excluded


def assert_plan_safe(
    foods: Iterable[FoodItem], age_months: int, allergens: Iterable[Allergen]
) -> None:
    """Raise ``UnsafePlanError`` if any planned food violates a rule. Second line of defence."""
    child_allergens = frozenset(allergens)
    problems = [
        f"{food.id}: {v.detail}"
        for food in foods
        for v in check_food(food, age_months, child_allergens)
    ]
    if problems:
        raise UnsafePlanError("; ".join(problems))
