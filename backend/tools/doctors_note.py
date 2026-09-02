"""Doctor's-note and preference rows: LLM extraction, deterministic application.

The language model does exactly one thing here -- turn the rows into candidate structures
(a numeric target per row, and the plain phrases of foods or food groups to avoid) -- and
its output is validated before use. Which targets count (doctor rows only, one per
nutrient), whether an override conflicts with the general target, and which value wins are
decided in plain Python (hard rule 3). Phrases are resolved to table foods by
``backend.nutrition.avoidance``, never used as free text. Any failure to extract degrades
to "row not applied, flagged", never to a blocked plan and never to a silently ignored row.
(Day 4 design Decision 8; child-notes-restrictions design Decision 4.)
"""

import json
import logging
import re
from collections.abc import Iterable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.chat import copy
from backend.models.enums import NoteKind
from backend.nutrition.foods import FoodCategory
from backend.nutrition.nutrients import REGISTRY
from backend.rag.retrievers import _content_text
from backend.schemas.tools import (
    UNIT_FOR_NUTRIENT,
    DoctorsNoteOverride,
    ExtractedAvoidance,
    NoteExtraction,
    NoteIssue,
    NoteRow,
    NoteTarget,
    NutrientTargets,
    OverrideOutcome,
)

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.05
MAX_PHRASES_PER_ROW = 10
MAX_PHRASE_CHARS = 80

# A row that opens with one of these is an instruction to leave something out. When the
# model returns nothing usable for such a row, the rest of the row is tried as the phrase --
# deterministic, and resolved against the table like any other phrase (design Decision 4).
_NEGATION_PREFIXES = ("no ", "avoid ", "never ", "skip ", "without ", "not ", "don't give ")

# The prompt's nutrient vocabulary and unit rules come from the registry's overridable rows,
# so the text the model sees and the validation that bounds its reply cannot drift apart.
_OVERRIDABLE = tuple(spec for spec in REGISTRY if spec.overridable)
_NUTRIENT_NAMES = ", ".join(f'"{spec.key}"' for spec in _OVERRIDABLE)
_UNIT_RULES = ", ".join(f'"{spec.unit}" for {spec.key}' for spec in _OVERRIDABLE)
_NUTRIENT_PHRASE = (
    ", ".join(spec.key for spec in _OVERRIDABLE[:-1]) + f", or {_OVERRIDABLE[-1].key}"
)
_CATEGORY_NAMES = ", ".join(
    category.value for category in FoodCategory if category is not FoodCategory.MILK_FEED
)

EXTRACT_SYSTEM_PROMPT = f"""You read numbered rows written about a child's diet. Each row is
tagged [doctor] or [preference]. For every row, extract (a) at most ONE numeric daily
nutrient instruction and (b) the foods or food groups the row says to avoid.

Return ONLY a JSON object of the form
{{"rows": [{{"row": <number>, "target": <object or null>, "avoid": [<string>, ...]}}, ...]}}
- "target": null, or an object with exactly these keys:
  "nutrient": one of {_NUTRIENT_NAMES}
  "direction": "max" (an upper limit: "no more than", "limit to", "under"),
               "min" (a lower limit: "at least", "no less than"),
               or "target" (a specific amount to aim for)
  "value": a positive number
  "unit": {_UNIT_RULES}
- "avoid": each entry is the food or food group the row names, as a short plain phrase
  WITHOUT words like "no", "avoid", "never" (e.g. "iron fortified oat cereal", "dairy").
  When a row means a whole food group, use exactly one of: {_CATEGORY_NAMES}.
  An empty list when the row leaves nothing out.

Rules:
- A row that names a food or food group to leave out ("no iron-fortified cereal", "avoid
  dairy", "never pork") is an avoidance, NEVER a target -- even when the food's name contains
  a nutrient word such as iron or protein. A target needs an explicit daily number written in
  the row; never invent a value, and never use 0.
- Convert units to the ones above if needed (e.g. 1 g = 1000 mg). Per-day values only; a
  per-kilogram or per-meal amount is not a target.
- Only a [doctor] row can carry a target; for a [preference] row "target" is always null.
- Advice about supplements, referrals, allergy testing, or timing is neither a target nor
  an avoidance.
- One entry per row, in order. Never add commentary. Output the JSON only."""


class _LlmRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=1)
    target: dict | None = None
    avoid: list[str] = Field(default_factory=list, max_length=MAX_PHRASES_PER_ROW)


class _LlmReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[_LlmRow]


def _clean_json(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = cleaned.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text[:120]!r}")
    return cleaned[start : end + 1]


def _parse_reply(text: str) -> _LlmReply:
    """The validated envelope, or raise. Row-level content is judged afterwards."""
    payload = json.loads(_clean_json(text))
    if not isinstance(payload, dict):
        raise ValueError("reply is not a JSON object")
    return _LlmReply.model_validate(payload)


def _numbered_rows(notes: Sequence[NoteRow]) -> str:
    return "\n".join(f"{i + 1}. [{row.kind.value}] {row.text}" for i, row in enumerate(notes))


# Direction words the model uses for the three the schema accepts; normalised before
# validation so a synonym is not a refused row. Anything else still fails validation.
_DIRECTION_SYNONYMS = {
    "max": "max",
    "maximum": "max",
    "limit": "max",
    "upper": "max",
    "cap": "max",
    "at most": "max",
    "no more than": "max",
    "min": "min",
    "minimum": "min",
    "lower": "min",
    "floor": "min",
    "at least": "min",
    "no less than": "min",
    "target": "target",
    "goal": "target",
    "aim": "target",
    "exact": "target",
}


def _normalise_target(payload: dict) -> dict:
    """Lower-case the vocabulary fields and map direction synonyms; values untouched."""
    cleaned = dict(payload)
    for key in ("nutrient", "direction", "unit"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = " ".join(cleaned[key].lower().split())
    if isinstance(cleaned.get("direction"), str):
        cleaned["direction"] = _DIRECTION_SYNONYMS.get(cleaned["direction"], cleaned["direction"])
    return cleaned


def _negated_phrase(text: str) -> str | None:
    """The rest of a row that opens with a negation word, or None."""
    lowered = text.lower()
    for prefix in _NEGATION_PREFIXES:
        if lowered.startswith(prefix):
            rest = text[len(prefix) :].strip(" .,;")
            return rest[:MAX_PHRASE_CHARS] or None
    return None


def _judge_rows(notes: Sequence[NoteRow], reply: _LlmReply) -> NoteExtraction:
    """Deterministic policy over the model's candidates (design Decision 4)."""
    targets: list[NoteTarget] = []
    avoid: list[ExtractedAvoidance] = []
    issues: list[NoteIssue] = []
    for item in reply.rows:
        index = item.row - 1
        if index >= len(notes):
            continue  # a row the model invented has nothing to attach to
        row = notes[index]
        row_targets = 0
        if item.target is not None:
            try:
                override = DoctorsNoteOverride.model_validate(_normalise_target(item.target))
            except ValidationError as exc:
                logger.info("Row %d target did not validate: %s", index, _first_error(exc))
                issues.append(NoteIssue(note_index=index, detail=copy.NOTE_TARGET_UNREADABLE))
            else:
                if row.kind is NoteKind.PREFERENCE:
                    issues.append(NoteIssue(note_index=index, detail=copy.NOTE_PREFERENCE_TARGET))
                else:
                    targets.append(NoteTarget(note_index=index, override=override))
                    row_targets += 1
        seen: set[str] = set()
        for phrase in item.avoid:
            phrase = " ".join(phrase.split())[:MAX_PHRASE_CHARS].strip()
            if phrase and phrase.lower() not in seen:
                seen.add(phrase.lower())
                avoid.append(ExtractedAvoidance(note_index=index, phrase=phrase))
        # "no iron fortified oat cereal" read as an iron target: the model gave nothing
        # usable, but the row plainly leaves something out -- try the rest of the row.
        if not seen and row_targets == 0 and (fallback := _negated_phrase(row.text)):
            avoid.append(ExtractedAvoidance(note_index=index, phrase=fallback))

    # One target per nutrient across all doctor rows; two rows on one nutrient are both
    # refused -- choosing between two prescriptions silently would be a guess.
    by_nutrient: dict[str, list[NoteTarget]] = {}
    for target in targets:
        by_nutrient.setdefault(target.override.nutrient, []).append(target)
    kept: list[NoteTarget] = []
    for nutrient, group in by_nutrient.items():
        if len(group) == 1:
            kept.extend(group)
            continue
        for target in group:
            issues.append(
                NoteIssue(
                    note_index=target.note_index, detail=copy.note_duplicate_nutrient(nutrient)
                )
            )
    kept.sort(key=lambda t: t.note_index)

    status = "applied" if kept or avoid else "nothing_to_apply"
    return NoteExtraction(status=status, targets=kept, avoid=avoid, issues=issues)


async def extract_notes(
    notes: Sequence[NoteRow], chat_model: BaseChatModel | None
) -> NoteExtraction:
    """Extract every row into bounded structures; degrade to ``unparsed`` on any failure."""
    if not notes:
        return NoteExtraction(status="not_present")
    if chat_model is None:
        logger.warning("Note rows present but no language model configured; not applied")
        return NoteExtraction(
            status="unparsed", detail="note extraction unavailable: no language model configured"
        )
    try:
        reply = await chat_model.ainvoke(
            [
                SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
                HumanMessage(content=_numbered_rows(notes)),
            ]
        )
        parsed = _parse_reply(_content_text(reply.content))
    except ValidationError as exc:
        logger.warning("Note extraction did not validate; not applied: %s", exc)
        return NoteExtraction(
            status="unparsed", detail=f"extraction did not validate: {_first_error(exc)}"
        )
    except Exception as exc:
        logger.warning("Note extraction failed; not applied: %s", exc)
        return NoteExtraction(status="unparsed", detail=f"extraction failed: {exc}")
    return _judge_rows(notes, parsed)


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


def apply_overrides(
    targets: NutrientTargets,
    overrides: Iterable[DoctorsNoteOverride],
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[NutrientTargets, list[OverrideOutcome]]:
    """``apply_override`` for each nutrient in turn (they are unique by construction)."""
    outcomes: list[OverrideOutcome] = []
    for override in overrides:
        targets, outcome = apply_override(targets, override, tolerance)
        outcomes.append(outcome)
    return targets, outcomes
