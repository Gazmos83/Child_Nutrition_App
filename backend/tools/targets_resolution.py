"""One definition of "the child's daily targets" (change 2 design Decision 5).

The meal planner, ``get_remaining_targets``, and ``detect_nutrient_gaps`` all measure
against the same thing: the DRI targets for this child with the doctor's note applied on
conflict (hard rule 3). Extracted from ``generate_meal_plan`` unchanged so that a
prescribed calorie limit is never reported as a deficit anywhere.
"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from backend.models.enums import Sex
from backend.nutrition.targets import (
    calculate_calorie_target,
    calculate_protein_target,
    iron_target,
)
from backend.schemas.tools import (
    ActivityLevel,
    CalorieTargetInput,
    NoteExtraction,
    NutrientTargets,
    OverrideOutcome,
    ProteinTargetInput,
)
from backend.tools.doctors_note import apply_override, extract_override


class ChildForTargets(Protocol):
    """The fields target resolution reads; satisfied by every tool request carrying a child."""

    @property
    def age_months(self) -> int: ...
    @property
    def weight_kg(self) -> float: ...
    @property
    def sex(self) -> Sex: ...
    @property
    def height_cm(self) -> float | None: ...
    @property
    def doctors_note(self) -> str | None: ...
    @property
    def activity_level(self) -> ActivityLevel: ...


def general_targets(child: ChildForTargets) -> NutrientTargets:
    """The DRI targets before any doctor's note."""
    return NutrientTargets(
        calories=calculate_calorie_target(
            CalorieTargetInput(
                age_months=child.age_months,
                weight_kg=child.weight_kg,
                sex=child.sex,
                height_cm=child.height_cm,
                activity_level=child.activity_level,
            )
        ),
        protein=calculate_protein_target(
            ProteinTargetInput(age_months=child.age_months, weight_kg=child.weight_kg)
        ),
        iron=iron_target(child.age_months),
    )


async def resolve_targets(
    child: ChildForTargets, chat_model: BaseChatModel | None
) -> tuple[NutrientTargets, NoteExtraction, OverrideOutcome]:
    """General targets -> note extraction -> deterministic override (note wins on conflict)."""
    general = general_targets(child)
    extraction = await extract_override(child.doctors_note, chat_model)
    targets, override = apply_override(general, extraction.override)
    return targets, extraction, override
