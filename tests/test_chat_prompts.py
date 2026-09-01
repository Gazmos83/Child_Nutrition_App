"""Prompt formatting for routing and tool-backed answers (Day 5 task 3.1)."""

import json

from backend.chat.prompts import (
    ANSWER_WITH_TOOLS_SYSTEM_PROMPT,
    NO_CHILD_CONTEXT_LINE,
    ROUTER_SYSTEM_PROMPT,
    build_tools_answer_prompt,
    format_child_context,
    format_history,
    format_tool_results,
)
from backend.schemas.chat import ChatTurn, ChildContext, ToolActivity


def test_both_system_prompts_name_growth_once() -> None:
    """day-6-growth-assessment task 3.1: the router and the answer prompt each carry
    exactly one growth passage, so a growth question reaches the tool, not the search."""
    assert ROUTER_SYSTEM_PROMPT.count("Growth questions") == 1
    assert "assess_growth" in ROUTER_SYSTEM_PROMPT
    assert "normal for their age" in ROUTER_SYSTEM_PROMPT
    assert ANSWER_WITH_TOOLS_SYSTEM_PROMPT.count("growth assessment") == 1
    assert "WHO label only when the band is not `expected`" in ANSWER_WITH_TOOLS_SYSTEM_PROMPT
    assert "snapshot" in ANSWER_WITH_TOOLS_SYSTEM_PROMPT


def test_answer_prompt_still_forbids_recomputation() -> None:
    assert "Never recompute" in ANSWER_WITH_TOOLS_SYSTEM_PROMPT


def test_child_block_lists_age_in_months_and_sorted_allergens() -> None:
    child = ChildContext.model_validate(
        {"age_months": 8, "weight_kg": 8.5, "sex": "female", "allergies": ["peanut", "egg"]}
    )
    block = format_child_context(child)
    assert "age: 8 months" in block
    assert "allergies: egg, peanut" in block
    assert "height: not given" in block
    assert "doctor's note: none" in block
    assert "years" not in block


def test_missing_child_is_stated_not_guessed() -> None:
    assert format_child_context(None) == NO_CHILD_CONTEXT_LINE
    assert "No child details supplied" in NO_CHILD_CONTEXT_LINE


def test_history_becomes_messages_in_order() -> None:
    turns = [ChatTurn(role="user", content="iron?"), ChatTurn(role="assistant", content="11 mg")]
    messages = format_history(turns)
    assert [m.type for m in messages] == ["human", "ai"]
    assert [m.content for m in messages] == ["iron?", "11 mg"]


def test_tool_results_are_labelled_json_blocks() -> None:
    ok = ToolActivity(name="calculate_bmi", status="ok", result={"bmi": 17.36})
    failed = ToolActivity(name="lookup_food", status="error", error="We don't know that food")
    text = format_tool_results([ok, failed])
    assert "Tool result 1 -- calculate_bmi (ok):" in text
    assert json.dumps({"bmi": 17.36}, indent=2) in text
    assert "Tool result 2 -- lookup_food (failed): We don't know that food" in text
    assert format_tool_results([]) == "(no tools were run)"


def test_answer_prompt_carries_context_tools_and_question() -> None:
    prompt = build_tools_answer_prompt("how much?", "[1] Source\ntext", [])
    assert (
        prompt.index("[1] Source")
        < prompt.index("(no tools were run)")
        < prompt.index("Question: how much?")
    )
    assert "answer from the tool results only" in build_tools_answer_prompt("q", "", [])
