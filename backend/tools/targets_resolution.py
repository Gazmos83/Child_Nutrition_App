"""One definition of "the child's daily targets" (change 2 design Decision 5).

The meal planner, ``get_remaining_targets``, and ``detect_nutrient_gaps`` all measure
against the same thing: the DRI targets for this child with the doctor's note applied on
conflict (hard rule 3).

Since day 9 the targets are the registry's displayed set, in display order, as one ordered
collection of uniform rows (design Decisions 1-2). ``NutrientTargets.calories``/``protein``/
``iron`` are computed views of the same rows, so every pre-existing consumer keeps its
three-field picture of the set this module now widens. Diet selects which rows appear and
their order; it never changes a number.
"""

from collections.abc import Sequence
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from backend.models.enums import ActivityLevel, DietPreference, Sex
from backend.nutrition.nutrients import TargetInputs, displayed_specs, evaluate
from backend.schemas.tools import (
    NoteExtraction,
    NoteRow,
    NutrientTarget,
    NutrientTargets,
    OverrideOutcome,
)
from backend.tools.doctors_note import apply_overrides, extract_notes


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
    def notes(self) -> Sequence[NoteRow]: ...
    @property
    def activity_level(self) -> ActivityLevel: ...
    @property
    def diet_preference(self) -> DietPreference: ...


def general_targets(child: ChildForTargets) -> NutrientTargets:
    """The DRI reference targets before any doctor's note, as the ordered displayed set."""
    diet = child.diet_preference
    inputs = TargetInputs(
        age_months=child.age_months,
        weight_kg=child.weight_kg,
        sex=child.sex,
        height_cm=child.height_cm,
        activity_level=child.activity_level,
    )
    rows = []
    for spec in displayed_specs(child.age_months, diet):
        evaluated = evaluate(spec, inputs)
        rows.append(
            NutrientTarget(
                nutrient=spec.key,
                label=spec.label,
                unit=spec.unit,
                amount=evaluated.amount,
                reference_type=evaluated.reference_type,
                band=evaluated.band,
                source=spec.source,
                upper_limit=evaluated.upper_limit,
                tracked=spec.tracked_for(diet),
                derivation=evaluated.derivation,
                per_kg=evaluated.per_kg,
                activity_level=evaluated.activity_level,
                advisory=evaluated.advisory,
                advisory_source_date=evaluated.advisory_source_date,
                display_note=spec.note_for(diet),
                not_tracked_reason=spec.not_tracked_reason or None,
            )
        )
    return NutrientTargets(items=tuple(rows))


async def resolve_targets(
    child: ChildForTargets, chat_model: BaseChatModel | None
) -> tuple[NutrientTargets, NoteExtraction, list[OverrideOutcome]]:
    """General targets -> note extraction -> deterministic overrides, one per nutrient the
    doctor's rows addressed (a row wins on conflict). An empty list means no override."""
    general = general_targets(child)
    extraction = await extract_notes(child.notes, chat_model)
    targets, overrides = apply_overrides(general, (t.override for t in extraction.targets))
    return targets, extraction, overrides
