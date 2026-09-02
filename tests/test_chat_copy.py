"""The parent-facing copy keeps its voice (Day 5 task 2.2; design.md Decision 13)."""

import inspect

from backend.chat import copy
from backend.models.enums import NoteKind
from backend.tools.meal_plan import NO_SAFE_PLAN_MESSAGE

CONSTANTS = {
    name: value for name, value in vars(copy).items() if name.isupper() and isinstance(value, str)
}
RENDERED = [
    *CONSTANTS.values(),
    copy.missing_field_hint("height"),
    copy.missing_field_hint("age_months"),
    copy.unknown_food("nope"),
    copy.wrong_unit("Avocado, mashed", "g", "ml"),
    copy.note_exclusion_reason(NoteKind.DOCTOR, "no honey"),
    copy.note_exclusion_reason(NoteKind.PREFERENCE, "no pork"),
    copy.note_no_match("kale chips"),
    copy.note_duplicate_nutrient("calories"),
    copy.avoidance_applied("dairy", 3),
    copy.avoidance_applied("pork", 1),
    NO_SAFE_PLAN_MESSAGE,
]


def test_every_string_is_present_and_calm() -> None:
    assert set(CONSTANTS) >= {
        "MISSING_CHILD_INFO_HINT",
        "SAFETY_STOP",
        "TOOL_FAILED",
        "STREAM_FAILED",
    }
    for text in RENDERED:
        assert text.strip(), text
        assert "!" not in text, text


def test_missing_field_hint_names_the_field_and_the_side_panel() -> None:
    hint = copy.missing_field_hint("height_cm")
    assert "height" in hint and "side panel" in hint
    assert "age in months" in copy.missing_field_hint("age_months")
    assert copy.missing_field_hint("serving_size").startswith("We need your child's serving size")


def test_unknown_food_quotes_the_identifier() -> None:
    assert "“nope”" in copy.unknown_food("nope")


def test_unknown_food_offers_the_suggested_names() -> None:
    text = copy.unknown_food("x", ["banana_mashed (Banana, mashed)"])
    assert "did you mean" in text
    assert "Banana, mashed" in text
    assert "banana_mashed" not in text  # the parent sees names, not slugs


def test_nothing_reads_as_a_missing_child() -> None:
    source = inspect.getsource(copy).lower()
    assert "missing child" not in source.replace("missing_child_info", "")
    for name in vars(copy):
        assert "missing_child_hint" not in name.lower()
    for text in RENDERED:
        assert "missing child" not in text.lower()


def test_no_safe_plan_headline_is_the_day_5_voice() -> None:
    assert NO_SAFE_PLAN_MESSAGE.startswith("We couldn't build a safe plan")
    assert "what you might want to check" in NO_SAFE_PLAN_MESSAGE
