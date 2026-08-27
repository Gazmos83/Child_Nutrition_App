"""``generate_meal_plan``: the composed child-facing tool (meal-plan-generation spec).

Pipeline, in order and without exception:

    validated request -> DRI targets -> doctor's-note override (``resolve_targets``)
    -> diet-preference filter
    -> infant-safety filter -> deterministic composition -> safety re-check -> totals
    -> disclaimer -> audit log

The language model is consulted for exactly one thing (turning a doctor's note into a
bounded override); every number and every inclusion/exclusion is deterministic. The safety
filter runs on the candidates *and* on the finished plan (design.md Decision 7). Every
call, including the no-safe-plan outcome, emits one JSON audit line (Decision 11).
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from backend.chat import copy as chat_copy
from backend.models.enums import Allergen, DietPreference
from backend.nutrition.diet import filter_by_diet
from backend.nutrition.feeding import normalise_entries, sum_totals
from backend.nutrition.foods import FoodCategory, FoodItem, LoadedFoodTable, get_food_table
from backend.nutrition.safety import assert_plan_safe, filter_foods
from backend.rag.prompts import DISCLAIMER
from backend.schemas.tools import (
    Adjustment,
    Exclusion,
    GapNutrient,
    MealItem,
    MealNutritionInput,
    MealPlanRequest,
    MealPlanResult,
    MealSlot,
    NoteExtraction,
    NutrientCoverage,
    NutrientGapReport,
    NutrientTargets,
    NutrientTotals,
    OverrideOutcome,
    PlannedItem,
)
from backend.tools.nutrient_tools import calculate_meal_nutrition
from backend.tools.targets_resolution import resolve_targets

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("backend.tools.audit")

# -- composition constants (design.md Decision 9) ---------------------------------------------

MAX_ITEMS = 8
MAX_SERVINGS_PER_SOLID = 3
CALORIE_FLOOR = 0.90  # stop filling once totals reach this share of the target
CALORIE_CEILING = 1.10  # never add a serving that would exceed this share
MILK_ONLY_UNTIL_MONTHS = 6  # WHO/AAP: exclusive milk feeding to about 6 months
MILK_ANCHOR_UNTIL_MONTHS = 12  # DGA: human milk or formula is the drink under 12 months
MILK_SHARE_6_TO_11 = 0.5  # WHO: milk remains a major energy source through 6-23 months
IRON_UL_MG = 40.0  # DRI tolerable upper intake level for iron, 0-13 years

# Change 2 (feeding log; design Decision 7). When today's logged intake leaves less than
# this share of the calorie target, there is nothing left to plan. Only a gap flagged at
# these confidences may steer composition; ``low`` is reported, never acted on.
TARGETS_MET_SHARE = 0.10
PRIORITY_CONFIDENCE = frozenset({"medium", "high"})

# WHO recommends breastfeeding; when both milk feeds are eligible the plan names breast
# milk and a parent using formula swaps it (Day 5 UI). Formula stays the fallback.
MILK_FEED_PRIORITY = ("breast_milk", "infant_formula_iron_fortified")

PROTEIN_FOODS = frozenset(
    {
        FoodCategory.LEGUME,
        FoodCategory.MEAT,
        FoodCategory.POULTRY,
        FoodCategory.FISH,
        FoodCategory.SHELLFISH,
        FoodCategory.EGG,
    }
)
# One food from each group first, so a plan is varied before it is topped up.
COVERAGE_GROUPS: tuple[tuple[str, frozenset[FoodCategory]], ...] = (
    ("grain", frozenset({FoodCategory.GRAIN})),
    ("vegetable", frozenset({FoodCategory.VEGETABLE})),
    ("fruit", frozenset({FoodCategory.FRUIT})),
    ("protein food", PROTEIN_FOODS),
    ("dairy", frozenset({FoodCategory.DAIRY})),
)
SOLID_SLOTS: tuple[MealSlot, ...] = ("breakfast", "lunch", "dinner", "snack")

# Parent-facing headline for the no-safe-plan outcome; the exclusions carry the "why"
# and the UI adds the "worth checking" list (Day 5 design.md Decision 13).
NO_SAFE_PLAN_MESSAGE = (
    "We couldn't build a safe plan with these details — here's why, and what you might "
    "want to check"
)


@dataclass
class _Draft:
    """Mutable plan under construction. Servings keyed by food id, insertion-ordered."""

    servings: dict[str, float]
    foods: dict[str, FoodItem]
    reasons: dict[str, str]
    calories: float = 0.0
    protein_g: float = 0.0
    iron_mg: float = 0.0

    def add(self, food: FoodItem, servings: float, reason: str) -> None:
        if food.id not in self.servings:
            self.servings[food.id] = 0.0
            self.foods[food.id] = food
            self.reasons[food.id] = reason
        self.servings[food.id] += servings
        self.calories += food.calories * servings
        self.protein_g += food.protein_g * servings
        self.iron_mg += food.iron_mg * servings

    def __len__(self) -> int:
        return len(self.servings)


def _composable(food: FoodItem) -> bool:
    """Planner preference, distinct from the safety filter: never *recommend* a sweetener
    (DGA: avoid added sugars under 2, limit after) or a food on the choking-hazard list,
    even at an age where the filter permits it. The filter's rule set is unchanged."""
    return not food.choking_hazard and food.category is not FoodCategory.SWEETENER


def _density_field(priority: GapNutrient | None) -> str:
    return "protein_g" if priority == "protein" else "iron_mg"


def _pick(candidates: Iterable[FoodItem], priority: GapNutrient | None = None) -> FoodItem | None:
    """Highest iron per serving -- or the priority nutrient's, when the log flagged one.
    Ties break on the lowest id, so choice is deterministic."""
    field = _density_field(priority)
    ranked = sorted(candidates, key=lambda f: (-getattr(f, field), f.id))
    return ranked[0] if ranked else None


def _half_servings(value: float) -> float:
    return max(0.5, round(value * 2) / 2)


def _compose(
    eligible: list[FoodItem],
    targets: NutrientTargets,
    age_months: int,
    priority: GapNutrient | None = None,
) -> _Draft:
    draft = _Draft(servings={}, foods={}, reasons={})
    ranked_by = "protein" if priority == "protein" else "iron"
    calorie_target = float(targets.calories.calories)
    ceiling = CALORIE_CEILING * calorie_target

    milk_feeds = [f for f in eligible if f.category is FoodCategory.MILK_FEED]
    solids = [f for f in eligible if f.category is not FoodCategory.MILK_FEED and _composable(f)]

    # 1. Milk anchor.
    if age_months < MILK_ANCHOR_UNTIL_MONTHS and milk_feeds:
        share = 1.0 if age_months < MILK_ONLY_UNTIL_MONTHS else MILK_SHARE_6_TO_11
        by_id = {f.id: f for f in milk_feeds}
        milk = next((by_id[i] for i in MILK_FEED_PRIORITY if i in by_id), None) or _pick(milk_feeds)
        assert milk is not None
        if milk.calories > 0:
            reason = (
                "milk feed: sole food before 6 months (WHO/AAP)"
                if share == 1.0
                else "milk feed: about half of daily energy at 6–11 months (WHO)"
            )
            draft.add(milk, _half_servings(calorie_target * share / milk.calories), reason)
    if age_months < MILK_ONLY_UNTIL_MONTHS:
        return draft  # No solids before 6 months, whatever the table says.

    # 2. Category coverage: one serving from each group, chosen for iron (or the priority).
    for label, categories in COVERAGE_GROUPS:
        if len(draft) >= MAX_ITEMS:
            break
        food = _pick((f for f in solids if f.category in categories), priority)
        if food is None or draft.calories + food.calories > ceiling:
            continue
        draft.add(food, 1.0, f"{label}; highest {ranked_by} among eligible {label} foods")

    # 3. Fill toward the calorie floor. While a protein or iron shortfall remains, close the
    #    larger one -- or the priority nutrient's, when the log flagged one and it is still
    #    short; once both targets are met, add calorie-dense foods not yet in the plan
    #    (variety) rather than piling on more iron. No serving may push iron past the DRI
    #    tolerable upper intake level.
    protein_target = targets.protein.protein_g
    iron_target_mg = targets.iron.iron_mg
    while draft.calories < CALORIE_FLOOR * calorie_target:
        protein_gap = _gap(draft.protein_g, protein_target)
        iron_gap = _gap(draft.iron_mg, iron_target_mg)
        candidates = [
            f
            for f in solids
            if draft.calories + f.calories <= ceiling
            and draft.iron_mg + f.iron_mg <= IRON_UL_MG
            and draft.servings.get(f.id, 0.0) < MAX_SERVINGS_PER_SOLID
            and (f.id in draft.servings or len(draft) < MAX_ITEMS)
        ]
        if not candidates:
            break
        if iron_gap == 0 and protein_gap == 0:
            food = sorted(candidates, key=lambda f: (f.id in draft.servings, -f.calories, f.id))[0]
            reason = "fills remaining energy; targets already met"
        elif priority == "protein" and protein_gap > 0:
            food = _best_fit(candidates, protein_target - draft.protein_g, lambda f: f.protein_g)
            reason = "fills protein shortfall (flagged by the feeding log)"
        elif priority == "iron" and iron_gap > 0:
            food = _best_fit(candidates, iron_target_mg - draft.iron_mg, lambda f: f.iron_mg)
            reason = "fills iron shortfall (flagged by the feeding log)"
        elif iron_gap >= protein_gap:
            food = _best_fit(candidates, iron_target_mg - draft.iron_mg, lambda f: f.iron_mg)
            reason = "fills iron shortfall"
        else:
            food = _best_fit(candidates, protein_target - draft.protein_g, lambda f: f.protein_g)
            reason = "fills protein shortfall"
        if food.calories <= 0:
            break
        draft.add(food, 1.0, reason)
    return draft


def _best_fit(candidates: list[FoodItem], need: float, contrib) -> FoodItem:
    """The smallest serving that closes ``need``; if none can, the largest contributor.

    Picking the biggest contributor outright overshoots (5 mg of iron to close a 1.6 mg
    gap); best-fit bounds the overshoot to one serving. Ties break on id.
    """
    closers = [f for f in candidates if contrib(f) >= need]
    if closers:
        return sorted(closers, key=lambda f: (contrib(f), f.id))[0]
    return sorted(candidates, key=lambda f: (-contrib(f), f.id))[0]


def _gap(current: float, target: float) -> float:
    return 0.0 if target <= 0 else max(0.0, (target - current) / target)


def _composition_targets(targets: NutrientTargets, already: NutrientTotals) -> NutrientTargets:
    """Full-day targets minus what was already eaten, floored at zero (design Decision 7)."""
    return targets.model_copy(
        update={
            "calories": targets.calories.model_copy(
                update={"calories": max(0, round(targets.calories.calories - already.calories))}
            ),
            "protein": targets.protein.model_copy(
                update={
                    "protein_g": round(max(0.0, targets.protein.protein_g - already.protein_g), 1)
                }
            ),
            "iron": targets.iron.model_copy(
                update={"iron_mg": round(max(0.0, targets.iron.iron_mg - already.iron_mg), 1)}
            ),
        }
    )


def _priority(gaps: NutrientGapReport | None) -> tuple[GapNutrient | None, Adjustment | None]:
    """The nutrient composition should favour, if the log flagged one with enough confidence.

    Only protein or iron can steer (a calorie gap is already what step 3 fills); a ``low``
    report is informational; targets are never touched here.
    """
    if gaps is None or gaps.status != "ok" or gaps.confidence not in PRIORITY_CONFIDENCE:
        return None, None
    for gap in gaps.gaps:
        if gap.flag == "below" and gap.nutrient in ("protein", "iron"):
            return gap.nutrient, Adjustment(
                nutrient=gap.nutrient,
                action="prioritised",
                confidence=gaps.confidence,
                window_days=gaps.window_days,
                detail=(
                    f"{gaps.window_days}-day average {gap.average:g} {gap.unit} against a "
                    f"{gap.target:g} {gap.unit} target; foods ranked by {gap.nutrient} per "
                    "serving, targets unchanged"
                ),
            )
    return None, None


def _items(draft: _Draft) -> list[PlannedItem]:
    items: list[PlannedItem] = []
    solid_index = 0
    for food_id, servings in draft.servings.items():
        food = draft.foods[food_id]
        if food.category is FoodCategory.MILK_FEED:
            slot: MealSlot = "milk feed"
        else:
            slot = SOLID_SLOTS[solid_index % len(SOLID_SLOTS)]
            solid_index += 1
        items.append(
            PlannedItem(
                food_id=food.id,
                name=food.name,
                servings=servings,
                serving_size=food.serving_size,
                serving_unit=food.serving_unit,
                meal=slot,
                reason=draft.reasons[food_id],
            )
        )
    return items


def _coverage(totals: NutrientTotals, targets: NutrientTargets) -> NutrientCoverage:
    def ratio(value: float, target: float) -> float:
        return round(value / target, 2) if target > 0 else 0.0

    return NutrientCoverage(
        calories=ratio(totals.calories, targets.calories.calories),
        protein=ratio(totals.protein_g, targets.protein.protein_g),
        iron=ratio(totals.iron_mg, targets.iron.iron_mg),
    )


def _message(
    request: MealPlanRequest,
    items: list[PlannedItem],
    totals: NutrientTotals,
    targets: NutrientTargets,
    already: NutrientTotals | None = None,
) -> str:
    solids = [i for i in items if i.meal != "milk feed"]
    if request.age_months < MILK_ONLY_UNTIL_MONTHS:
        lead = (
            "Before about 6 months, breast milk or iron-fortified formula is the only food "
            "a baby needs; this plan is milk feeds only."
        )
    elif not solids:
        lead = "Only milk feeds could be included: no eligible solid foods remained."
    else:
        lead = f"A one-day plan with {len(solids)} foods chosen for iron and variety."
    rest = (
        f" This covers the rest of the day after {already.calories:.0f} kcal already logged."
        if already is not None
        else ""
    )
    return (
        f"{lead} Totals: about {totals.calories:.0f} kcal of a {targets.calories.calories} kcal "
        f"target, {totals.protein_g:.1f} g protein of {targets.protein.protein_g:.1f} g, and "
        f"{totals.iron_mg:.1f} mg iron of {targets.iron.iron_mg:.1f} mg.{rest}"
    )


def _audit(
    request: MealPlanRequest,
    outcome: str,
    targets: NutrientTargets,
    extraction: NoteExtraction,
    override: OverrideOutcome,
    exclusions: list[Exclusion],
    items: list[PlannedItem],
    totals: NutrientTotals,
    table_version: str,
    already_logged: NutrientTotals | None = None,
    adjustments: list[Adjustment] | None = None,
) -> None:
    gaps = request.gaps
    record = {
        "event": "meal_plan",
        "outcome": outcome,
        "input": {
            "age_months": request.age_months,
            "weight_kg": request.weight_kg,
            "height_cm": request.height_cm,
            "sex": request.sex.value,
            "diet_preference": request.diet_preference.value,
            "allergies": sorted(a.value for a in request.allergies),
            "doctors_note": request.doctors_note,
            "activity_level": request.activity_level.value,
        },
        "targets": {
            "calories": {
                "value": targets.calories.calories,
                "band": targets.calories.band,
                "source": targets.calories.source,
            },
            "protein_g": {
                "value": targets.protein.protein_g,
                "band": targets.protein.band,
                "source": targets.protein.source,
            },
            "iron_mg": {
                "value": targets.iron.iron_mg,
                "band": targets.iron.band,
                "source": targets.iron.source,
            },
        },
        "note_extraction": extraction.model_dump(mode="json"),
        "override": override.model_dump(mode="json"),
        "exclusions": [e.model_dump(mode="json") for e in exclusions],
        "items": [{"food_id": i.food_id, "servings": i.servings} for i in items],
        "totals": totals.model_dump(mode="json"),
        "food_table_version": table_version,
        # Change 2 (hard rule 8, §9b): what from the feeding log informed this plan.
        "gaps": (
            {
                "status": gaps.status,
                "confidence": gaps.confidence,
                "days_logged": gaps.days_logged,
                "window_days": gaps.window_days,
                "flags": {g.nutrient: g.flag for g in gaps.gaps},
            }
            if gaps is not None
            else None
        ),
        "logged_today": (
            {
                "entries": [
                    {
                        "id": e.id,
                        "fed_at": e.fed_at.isoformat(),
                        "feeding_type": e.feeding_type.value,
                        "food_id": e.food_id,
                    }
                    for e in request.logged_today
                ],
                "already_logged": already_logged.model_dump(mode="json"),
            }
            if already_logged is not None
            else None
        ),
        "adjustments": [a.model_dump(mode="json") for a in adjustments or []],
        "rules": [
            "no_honey_under_12_months",
            "no_choking_hazard_under_4_years",
            "no_unpasteurized_products",
            "no_recorded_allergen",
            "below_minimum_age",
            f"diet_preference:{request.diet_preference.value}",
        ],
    }
    audit_logger.info("meal_plan_audit %s", json.dumps(record, sort_keys=True))


async def generate_meal_plan(
    request: MealPlanRequest,
    chat_model: BaseChatModel | None,
    table: LoadedFoodTable | None = None,
) -> MealPlanResult:
    """Compose a one-day plan for the child described by ``request``.

    ``request`` has already been validated by Pydantic, so nothing here runs for an
    out-of-range age or weight. ``chat_model`` may be ``None``: a doctor's note is then
    reported as not applied and the plan still generates.
    """
    table = table or get_food_table()
    age: int = request.age_months
    allergens: frozenset[Allergen] = request.allergies
    preference: DietPreference = request.diet_preference

    targets, extraction, override = await resolve_targets(request, chat_model)

    # Change 2: the log may narrow what is left to cover and which nutrient to favour.
    # Neither touches ``targets`` -- the day's targets stay the reference (Decision 7).
    already_logged: NutrientTotals | None = None
    composition_targets = targets
    if request.logged_today:
        logged = normalise_entries(request.logged_today, table)
        already_logged = sum_totals(e.nutrients for e in logged)
        composition_targets = _composition_targets(targets, already_logged)
    priority, adjustment = _priority(request.gaps)
    adjustments = [adjustment] if adjustment else []

    diet_ok, diet_excluded = filter_by_diet(table.foods, preference)
    safe, safety_excluded = filter_foods(diet_ok, age, allergens)
    exclusions = [
        Exclusion(food_id=f.id, reasons=[f"not part of a {preference.value} diet"])
        for f in diet_excluded
    ] + [Exclusion(food_id=e.food.id, reasons=e.reasons) for e in safety_excluded]

    zero = NutrientTotals(
        calories=0, protein_g=0, fat_g=0, carbohydrate_g=0, iron_mg=0, calcium_mg=0
    )
    if (
        already_logged is not None
        and composition_targets.calories.calories < TARGETS_MET_SHARE * targets.calories.calories
    ):
        _audit(
            request,
            "targets_met",
            targets,
            extraction,
            override,
            exclusions,
            [],
            zero,
            table.version,
            already_logged,
            adjustments,
        )
        return MealPlanResult(
            outcome="targets_met",
            items=[],
            totals=zero,
            targets=targets,
            coverage=_coverage(zero, composition_targets),
            note_extraction=extraction,
            override=override,
            exclusions=exclusions,
            message=chat_copy.TARGETS_MET_MESSAGE,
            disclaimer=DISCLAIMER,
            food_table_version=table.version,
            adjustments=adjustments,
            already_logged=already_logged,
        )

    draft = _compose(safe, composition_targets, age, priority)
    items = _items(draft)

    # Second line of defence (hard rule 4): the finished plan is re-checked, unconditionally.
    assert_plan_safe(draft.foods.values(), age, allergens)

    if items:
        nutrition = calculate_meal_nutrition(
            MealNutritionInput(
                items=[MealItem(food_id=i.food_id, servings=i.servings) for i in items]
            ),
            table,
        )
        totals = nutrition.totals
        outcome = "plan"
        message = _message(request, items, totals, composition_targets, already_logged)
    else:
        totals = zero
        outcome = "no_safe_plan"
        message = NO_SAFE_PLAN_MESSAGE
        logger.warning(
            "No safe meal plan: age=%d preference=%s allergies=%s excluded=%d",
            age,
            preference.value,
            sorted(a.value for a in allergens),
            len(exclusions),
        )

    _audit(
        request,
        outcome,
        targets,
        extraction,
        override,
        exclusions,
        items,
        totals,
        table.version,
        already_logged,
        adjustments,
    )

    return MealPlanResult(
        outcome=outcome,  # type: ignore[arg-type]
        items=items,
        totals=totals,
        targets=targets,
        coverage=_coverage(totals, composition_targets),
        note_extraction=extraction,
        override=override,
        exclusions=exclusions,
        message=message,
        disclaimer=DISCLAIMER,
        food_table_version=table.version,
        adjustments=adjustments,
        already_logged=already_logged,
    )
