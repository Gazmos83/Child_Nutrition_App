"""Server-originated, parent-facing strings (design.md Decision 13).

Every message the backend itself writes to a parent lives here, so the voice can be
reviewed in one place. Tone: warm and unhurried by default; direct -- what happened, what
it means, what to do next, no wordplay -- for anything touching safety, allergies, a
doctor's instruction, or an error. Names describe the missing *information*, never the
child. The Day 3 RAG prompt, ``DISCLAIMER``, and ``NO_ANSWER_MESSAGE`` are frozen for the
Day 6 evaluation and deliberately do not live here.
"""

from collections.abc import Sequence

from backend.models.enums import NoteKind

MISSING_CHILD_INFO_HINT = "Your little one's details go in the side panel — then we're good to go"

SAFETY_STOP = (
    "We stopped this plan because a safety check didn't pass. That's on us, not you — "
    "nothing unsafe was shown. Please try once more"
)

TOOL_FAILED = "That one didn't work out on our side. Everything else in this answer still stands"
SERVER_ERROR = "Something went wrong on our side. If it keeps happening, quote the request id"
RATE_LIMITED = "That's a lot of requests in a short time. Give it a minute, then try again"

STREAM_FAILED = (
    "We lost the thread mid-answer. Please try again — your child's details are safe in "
    "the side panel"
)

# How a tool argument is named when we ask the parent for it.
FIELD_LABELS: dict[str, str] = {
    "age_months": "age in months",
    "weight_kg": "weight",
    "height_cm": "height",
    "sex": "sex",
    "diet_preference": "diet preference",
    "allergies": "allergies",
    "notes": "doctor's note and preferences",
    "activity_level": "activity level",
    "food_id": "food",
    "items": "meal items",
}


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " "))


def missing_field_hint(field: str) -> str:
    return (
        f"We need your child's {field_label(field)} for this one — pop it in the side panel "
        "and we'll take it from there"
    )


def unknown_food(food_id: str, suggestions: Sequence[str] = ()) -> str:
    if suggestions:
        names = ", ".join(_display_name(s) for s in suggestions)
        return f"We don't know a food called “{food_id}” — did you mean {names}?"
    return f"We don't know a food called “{food_id}” yet"


# Hard rule 10: a live external match is informational only, never a pediatric-guideline
# citation and never usable in a meal plan -- direct, since it borders on safety.
EXTERNAL_FOOD_DISCLAIMER = (
    "This is third-party nutrition data, not one of our reviewed pediatric sources — it "
    "can't be used in a meal plan until an administrator adds it to the food table"
)


def wrong_unit(food_name: str, expected_unit: str, given_unit: str) -> str:
    """An amount in a unit the food is not measured in (food-lookup-quantities)."""
    return (
        f"{food_name} is measured in {expected_unit}, not {given_unit} — give the amount in "
        f"{expected_unit} and we'll work it out"
    )


def _display_name(suggestion: str) -> str:
    """The human name from a ``"id (Name)"`` suggestion, or the string as given."""
    open_paren = suggestion.find("(")
    if open_paren != -1 and suggestion.endswith(")"):
        return suggestion[open_paren + 1 : -1]
    return suggestion


# Note rows (child-notes-restrictions): every row gets an outcome the parent can read. Direct
# voice -- a doctor's instruction is never a joke.
NOTE_PREFERENCE_TARGET = (
    "Only a doctor's note can change a target; this row's food exclusions still apply"
)
NOTE_MILK_FEED = (
    "Breast milk and formula are never left out by a note — please talk to your pediatrician "
    "about milk feeds"
)
NOTE_TARGET_UNREADABLE = (
    "We couldn't read a daily target from this row — a target needs a nutrient, a direction, "
    "and a daily number"
)
NOTE_NOTHING = (
    "Nothing here we could act on — a target needs a daily number, and leaving a food out "
    "needs the food or food group named"
)
NOTE_EXTRACTION_UNAVAILABLE = (
    "We couldn't read the notes this time; the plan uses the general targets"
)


def note_exclusion_reason(kind: NoteKind, text: str) -> str:
    whose = "your doctor's note" if kind is NoteKind.DOCTOR else "your preference"
    return f"left out by {whose}: “{text}”"


def note_no_match(phrase: str) -> str:
    return (
        f"We don't have a food or food group called “{phrase}” in our table, so this row "
        "wasn't applied"
    )


def note_duplicate_nutrient(label: str) -> str:
    return f"More than one doctor row sets {label}; neither was applied — keep one"


def avoidance_applied(phrase: str, count: int) -> str:
    foods = "one food" if count == 1 else f"{count} foods"
    return f"“{phrase}” left {foods} out of the plan"


# Growth assessment: reasons an indicator is skipped, never failed (growth-assessment spec).
# Location-neutral on purpose: the same result renders in the chat card and in a growth-log
# row (growth-tracking spec).
GROWTH_NEEDS_HEIGHT = (
    "We need your child's length or height for this one — add it and we'll place it on the "
    "WHO chart"
)


def GROWTH_HEIGHT_OUT_OF_RANGE(lo_cm: float, hi_cm: float) -> str:  # noqa: N802 — copy name
    """Names the covered range, so the parent can see why the number sits outside it."""
    return (
        f"The WHO weight-for-length/height table covers {lo_cm:g}–{hi_cm:g} cm, so we "
        "couldn't place this measurement on it — the other indicators still stand"
    )


# The meal planner's ``targets_met`` outcome (change 2 design Decisions 7 and 12).
TARGETS_MET_MESSAGE = (
    "Today's already covered — what you've logged meets the day's targets. Nothing more to "
    "plan; enjoy the rest of it"
)
