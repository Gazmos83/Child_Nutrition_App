"""Server-originated, parent-facing strings (design.md Decision 13).

Every message the backend itself writes to a parent lives here, so the voice can be
reviewed in one place. Tone: warm and unhurried by default; direct -- what happened, what
it means, what to do next, no wordplay -- for anything touching safety, allergies, a
doctor's instruction, or an error. Names describe the missing *information*, never the
child. The Day 3 RAG prompt, ``DISCLAIMER``, and ``NO_ANSWER_MESSAGE`` are frozen for the
Day 6 evaluation and deliberately do not live here.
"""

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
    "doctors_note": "doctor's note",
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


def unknown_food(food_id: str) -> str:
    return f"We don't know a food called “{food_id}” yet — try picking one from the list"


# Growth assessment: reasons an indicator is skipped, never failed (growth-assessment spec).
GROWTH_NEEDS_HEIGHT = (
    "We need your child's length or height for this one — pop it in the side panel and "
    "we'll place it on the WHO chart"
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
