"""Routing decisions and the context seam (Day 5 task 3.2; intent-routing spec)."""

import logging

from langchain_core.messages import AIMessage

from backend.chat.router import MAX_TOOL_CALLS, SEARCH_TOOL_NAME, decide, resolve_context
from backend.schemas.chat import ChatRequest
from backend.schemas.tools import BmiInput, MealPlanRequest, ProteinTargetInput
from backend.tools.langchain_tools import build_tools
from tests.fixtures.fake_llm import RecordingChatModel

CHILD = {"age_months": 8, "weight_kg": 8.5, "sex": "female", "allergies": ["peanut"]}


def call(name: str, **args) -> dict:
    return {"name": name, "args": args, "id": f"id-{name}", "type": "tool_call"}


def reply(*calls: dict, text: str = "") -> AIMessage:
    return AIMessage(content=text, tool_calls=list(calls))


async def route(*calls: dict, text: str = "", **request_fields) -> tuple:
    llm = RecordingChatModel(responses=[reply(*calls, text=text)])
    request = ChatRequest.model_validate({"message": "how much protein?", **request_fields})
    return await decide(llm, build_tools(None), request), llm


class TestIntentMapping:
    async def test_search_only_is_rag(self) -> None:
        decision, _ = await route(call(SEARCH_TOOL_NAME, query="iron needs for infants"))
        assert decision.intent == "rag"
        assert decision.search_query == "iron needs for infants"
        assert decision.calls == [] and decision.planned == [SEARCH_TOOL_NAME]

    async def test_tools_only_is_tool(self) -> None:
        decision, _ = await route(call("calculate_protein_target", age_months=8, weight_kg=8.5))
        assert decision.intent == "tool"
        assert decision.search_query is None
        assert [c.name for c in decision.calls] == ["calculate_protein_target"]

    async def test_both_is_hybrid(self) -> None:
        decision, _ = await route(
            call("calculate_protein_target", age_months=8, weight_kg=8.5),
            call(SEARCH_TOOL_NAME, query="why iron matters at 8 months"),
        )
        assert decision.intent == "hybrid"
        assert decision.planned == ["calculate_protein_target", SEARCH_TOOL_NAME]

    async def test_nothing_selected_falls_back_to_rag_on_the_message(self) -> None:
        decision, _ = await route(text="Sure! Protein is important.")
        assert decision.intent == "rag"
        assert decision.search_query == "how much protein?"
        assert decision.planned == []

    async def test_unknown_tool_is_ignored(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="backend.chat.router"):
            decision, _ = await route(call("order_pizza", size="large"))
        assert decision.intent == "rag" and decision.calls == []
        assert "unknown tool 'order_pizza'" in caplog.text


class TestCap:
    async def test_six_calls_truncate_to_four_and_log(self, caplog) -> None:
        calls = [call("calculate_bmi", weight_kg=9, height_cm=72) for _ in range(6)]
        with caplog.at_level(logging.INFO, logger="backend.chat.router"):
            decision, _ = await route(*calls)
        assert len(decision.calls) == MAX_TOOL_CALLS == 4
        assert decision.dropped == 2
        assert "dropped 2 tool call(s)" in caplog.text


class TestResolveContext:
    def test_child_context_overrides_model_weight(self, caplog) -> None:
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        with caplog.at_level(logging.INFO, logger="backend.chat.router"):
            args, used = resolve_context(
                "calculate_protein_target",
                {"age_months": 9, "weight_kg": 9.0},
                request,
                ProteinTargetInput,
            )
        assert args == {"age_months": 8, "weight_kg": 8.5}
        assert "weight_kg" in used and "age_months" in used
        assert "context wins" in caplog.text

    def test_enums_and_sets_become_json_values(self) -> None:
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        args, used = resolve_context("generate_meal_plan", {}, request, MealPlanRequest)
        assert args["sex"] == "female" and args["allergies"] == ["peanut"]
        assert args["diet_preference"] == "omnivore"
        assert "height_cm" not in args  # child has none recorded; tool keeps its own default
        assert set(used) >= {"age_months", "weight_kg", "sex", "allergies", "diet_preference"}

    def test_model_height_is_dropped_when_child_has_none(self) -> None:
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        args, _ = resolve_context(
            "calculate_bmi", {"weight_kg": 9, "height_cm": 72}, request, BmiInput
        )
        assert args == {"weight_kg": 8.5}  # the invented height never survives

    def test_pass_through_without_child(self) -> None:
        request = ChatRequest.model_validate({"message": "m"})
        args, used = resolve_context(
            "calculate_bmi", {"weight_kg": 9, "height_cm": 72}, request, BmiInput
        )
        assert args == {"weight_kg": 9, "height_cm": 72} and used == []


class TestRoutingPrompt:
    async def test_prompt_contains_child_block_and_history(self) -> None:
        history = [
            {"role": "user", "content": "how much iron does she need?"},
            {"role": "assistant", "content": "About 11 mg a day [1]."},
        ]
        _, llm = await route(
            call(SEARCH_TOOL_NAME, query="calories 8 months"), child=CHILD, history=history
        )
        assert set(llm.bound_tools) >= {"calculate_bmi", "generate_meal_plan", SEARCH_TOOL_NAME}
        messages = llm.calls[0]
        assert "age: 8 months" in messages[0].content and "allergies: peanut" in messages[0].content
        assert [m.type for m in messages] == ["system", "human", "ai", "human"]
        assert messages[1].content == "how much iron does she need?"
        assert messages[-1].content == "how much protein?"

    async def test_prompt_states_missing_child(self) -> None:
        _, llm = await route(call(SEARCH_TOOL_NAME, query="q"))
        assert "No child details supplied" in llm.calls[0][0].content
