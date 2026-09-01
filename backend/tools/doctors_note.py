"""Doctor's-note override: LLM extraction, deterministic application (Decision 8).

The language model does exactly one thing here -- turn free text into a candidate
``DoctorsNoteOverride`` -- and its output is validated before use. Whether the override
conflicts with the general target, and which value wins, is decided by ``apply_override``
in plain Python (hard rule 3). Any failure to extract degrades to "note not applied,
flagged", never to a blocked plan and never to a silently ignored note.
"""

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from backend.nutrition.nutrients import REGISTRY
from backend.rag.retrievers import _content_text
from backend.schemas.tools import (
    UNIT_FOR_NUTRIENT,
    DoctorsNoteOverride,
    NoteExtraction,
    NutrientTargets,
    OverrideOutcome,
)

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.05

# The prompt's nutrient vocabulary and unit rules come from the registry's overridable rows,
# so the text the model sees and the validation that bounds its reply cannot drift apart.
_OVERRIDABLE = tuple(spec for spec in REGISTRY if spec.overridable)
_NUTRIENT_NAMES = ", ".join(f'"{spec.key}"' for spec in _OVERRIDABLE)
_UNIT_RULES = ", ".join(f'"{spec.unit}" for {spec.key}' for spec in _OVERRIDABLE)
_NUTRIENT_PHRASE = (
    ", ".join(spec.key for spec in _OVERRIDABLE[:-1]) + f", or {_OVERRIDABLE[-1].key}"
)

EXTRACT_SYSTEM_PROMPT = f"""You read a short note written by a child's doctor and extract ONE
numeric daily nutrient instruction from it, if there is one.

Return ONLY a JSON object with exactly these keys, or the JSON value null if the note
contains no numeric daily target for one of the supported nutrients:
- "nutrient": one of {_NUTRIENT_NAMES}
- "direction": "max" (an upper limit: "no more than", "limit to", "under"),
               "min" (a lower limit: "at least", "no less than"),
               or "target" (a specific amount to aim for)
- "value": a positive number
- "unit": {_UNIT_RULES}

Rules:
- Convert units to the ones above if needed (e.g. 1 g = 1000 mg).
- Per-day values only. If the note gives a per-kilogram or per-meal amount and no daily
  amount, return null.
- If the note mentions several nutrients, choose the one stated most explicitly as a
  number; do not invent values for the others.
- Advice about foods, allergies, supplements, or referrals is not a nutrient target:
  return null.
- Never add commentary. Output the JSON only."""


def _parse_override(text: str) -> DoctorsNoteOverride | None:
    """A validated override, or ``None`` for an explicit null. Raises on anything else."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = cleaned.strip()
    if cleaned.lower() == "null":
        return None
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text[:120]!r}")
    payload = json.loads(cleaned[start : end + 1])
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("reply is not a JSON object")
    return DoctorsNoteOverride.model_validate(payload)


async def extract_override(note: str | None, chat_model: BaseChatModel | None) -> NoteExtraction:
    """Extract the note into a bounded override; degrade to ``unparsed`` on any failure."""
    if note is None or not note.strip():
        return NoteExtraction(status="not_present")
    if chat_model is None:
        logger.warning("Doctor's note present but no language model configured; not applied")
        return NoteExtraction(
            status="unparsed", detail="note extraction unavailable: no language model configured"
        )
    try:
        reply = await chat_model.ainvoke(
            [SystemMessage(content=EXTRACT_SYSTEM_PROMPT), HumanMessage(content=note.strip())]
        )
        override = _parse_override(_content_text(reply.content))
    except ValidationError as exc:
        logger.warning("Doctor's note extraction did not validate; not applied: %s", exc)
        return NoteExtraction(
            status="unparsed", detail=f"extraction did not validate: {_first_error(exc)}"
        )
    except Exception as exc:
        logger.warning("Doctor's note extraction failed; not applied: %s", exc)
        return NoteExtraction(status="unparsed", detail=f"extraction failed: {exc}")
    if override is None:
        return NoteExtraction(
            status="no_numeric_target",
            detail=f"the note contains no numeric daily target for {_NUTRIENT_PHRASE}",
        )
    return NoteExtraction(status="applied", override=override)


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    loc = ".".join(str(p) for p in first["loc"]) or "value"
    return f"{loc}: {first['msg']}"


def apply_override(
    targets: NutrientTargets,
    override: DoctorsNoteOverride | None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[NutrientTargets, OverrideOutcome]:
    """Deterministic precedence: on conflict the note wins outright; never a blend.

    ``max`` conflicts when the general value exceeds it; ``min`` when the general value is
    below it; ``target`` when the two differ by more than ``tolerance`` (relative). With no
    conflict the general value is kept and the override is still recorded.
    """
    if override is None:
        return targets, OverrideOutcome(conflict=False, source="general_target")

    general = targets.amount_of(override.nutrient)
    unit = UNIT_FOR_NUTRIENT[override.nutrient]
    conflict = False
    if override.direction == "max":
        conflict = general > override.value
    elif override.direction == "min":
        conflict = general < override.value
    else:
        conflict = abs(general - override.value) > tolerance * max(override.value, 1e-9)

    if not conflict:
        return targets, OverrideOutcome(
            conflict=False,
            source="general_target",
            nutrient=override.nutrient,
            general_value=general,
            applied_value=general,
            detail=(
                f"doctor's note ({override.direction} {override.value:g} {unit}) is consistent "
                f"with the general target of {general:g} {unit}"
            ),
        )

    applied = targets.with_amount(
        override.nutrient,
        override.value,
        source="doctor's note (overrides general target)",
        derivation="doctor's note",
    )
    return applied, OverrideOutcome(
        conflict=True,
        source="doctors_note",
        nutrient=override.nutrient,
        general_value=general,
        applied_value=override.value,
        detail=(
            f"doctor's note ({override.direction} {override.value:g} {unit}) conflicts with the "
            f"general target of {general:g} {unit}; the note's value is used"
        ),
    )
