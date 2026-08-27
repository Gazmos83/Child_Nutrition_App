"""Tool execution and answer composition (Day 5 tasks 3.3, 4.1)."""

import logging

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from backend.chat import copy
from backend.chat.router import SEARCH_TOOL_NAME
from backend.chat.service import ChatService, run_tools
from backend.db.knowledge_store import Document
from backend.nutrition.safety import UnsafePlanError
from backend.rag.pipeline import RagPipeline
from backend.rag.prompts import DISCLAIMER
from backend.rag.retrievers import AdvancedRetriever, BasicRetriever
from backend.schemas.chat import ChatRequest, PlannedCall, RouteDecision
from backend.schemas.tools import MealPlanRequest, MealPlanResult, ProteinTargetInput
from backend.tools.langchain_tools import build_tools
from backend.tools.nutrient_tools import calculate_protein_target
from tests.fixtures.fake_llm import RecordingChatModel
from tests.fixtures.memory_store import InMemoryKnowledgeStore

CHILD = {"age_months": 8, "weight_kg": 8.5, "sex": "female", "allergies": ["peanut"]}
IRON_QUESTION = "how much iron do infants need each day"
CORPUS = [
    Document(
        content="Infants 7 to 12 months need 11 mg of iron each day",
        source="Iron Source",
        date=2010,
        topic="iron",
        section="Needs",
        document_id="iron",
        age_min_months=7,
        age_max_months=12,
    ),
]
ANSWER = "Babies 7–12 months need 11 mg of iron a day [1]."


def call(name: str, **args) -> dict:
    return {"name": name, "args": args, "id": f"id-{name}", "type": "tool_call"}


def decision(*calls: PlannedCall, intent: str = "tool") -> RouteDecision:
    return RouteDecision(
        intent=intent, calls=list(calls), planned=[c.name for c in calls], search_query=None
    )


@pytest.fixture
def tools():
    return {t.name: t for t in build_tools(None)}


def make_service(responses: list) -> tuple[ChatService, RecordingChatModel]:
    llm = RecordingChatModel(responses=responses)
    store = InMemoryKnowledgeStore(CORPUS)
    pipeline = RagPipeline(
        retrievers={"basic": BasicRetriever(store), "advanced": AdvancedRetriever(store, None)},
        chat_model=llm,
    )
    return ChatService(pipeline, llm, build_tools(None)), llm


async def collect(service: ChatService, request: ChatRequest) -> list[tuple[str, dict]]:
    return [(e.event, e.data) async for e in service.stream(request)]


class TestRunTools:
    async def test_bad_food_fails_alone_while_sibling_succeeds(self, tools) -> None:
        request = ChatRequest.model_validate({"message": "m"})
        activities = await run_tools(
            decision(
                PlannedCall(name="lookup_food", args={"food_id": "nope"}),
                PlannedCall(name="calculate_bmi", args={"weight_kg": 9, "height_cm": 72}),
            ),
            request,
            tools,
        )
        failed, ok = activities
        assert failed.status == "error" and failed.error == copy.unknown_food("nope")
        assert "nope" in (failed.detail or "")
        assert ok.status == "ok" and ok.result == {
            **ok.result,
            "bmi": 17.36,
        }

    async def test_missing_age_without_child_gives_the_side_panel_hint(self, tools) -> None:
        request = ChatRequest.model_validate({"message": "m"})
        [activity] = await run_tools(
            decision(PlannedCall(name="calculate_protein_target", args={"weight_kg": 8.5})),
            request,
            tools,
        )
        assert activity.status == "error"
        assert activity.error == copy.MISSING_CHILD_INFO_HINT
        assert activity.detail and "age_months" in activity.detail

    async def test_bmi_without_height_with_child_names_height(self, tools) -> None:
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        [activity] = await run_tools(
            decision(PlannedCall(name="calculate_bmi", args={"weight_kg": 9, "height_cm": 72})),
            request,
            tools,
        )
        assert activity.status == "error"
        assert activity.error == copy.missing_field_hint("height")
        assert activity.args == {"weight_kg": 8.5} and activity.used_context == ["weight_kg"]

    async def test_out_of_range_model_argument_is_a_generic_failure(self, tools) -> None:
        request = ChatRequest.model_validate({"message": "m"})
        [activity] = await run_tools(
            decision(
                PlannedCall(
                    name="calculate_protein_target", args={"age_months": 72, "weight_kg": 20}
                )
            ),
            request,
            tools,
        )
        assert activity.status == "error" and activity.error == copy.TOOL_FAILED
        assert "age_months" in (activity.detail or "")

    async def test_unsafe_plan_is_a_safety_stop(self, tools) -> None:
        async def boom(**kwargs):
            raise UnsafePlanError("honey slipped through")

        tools["generate_meal_plan"] = StructuredTool.from_function(
            coroutine=boom, name="generate_meal_plan", description="x", args_schema=MealPlanRequest
        )
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        [activity] = await run_tools(
            decision(PlannedCall(name="generate_meal_plan", args={})), request, tools
        )
        assert activity.status == "error" and activity.error == copy.SAFETY_STOP
        assert activity.detail == "honey slipped through"

    async def test_meal_plan_result_round_trips(self, tools) -> None:
        request = ChatRequest.model_validate({"message": "m", "child": CHILD})
        [activity] = await run_tools(
            decision(PlannedCall(name="generate_meal_plan", args={})), request, tools
        )
        assert activity.status == "ok"
        plan = MealPlanResult.model_validate(activity.result)
        assert plan.outcome == "plan" and plan.disclaimer == DISCLAIMER
        assert not any("peanut" in item.food_id for item in plan.items)
        assert set(activity.used_context) >= {"age_months", "weight_kg", "sex", "allergies"}


class TestStream:
    async def test_rag_path_matches_the_pipeline_exactly(self) -> None:
        service, _ = make_service(
            [
                AIMessage(content="", tool_calls=[call(SEARCH_TOOL_NAME, query=IRON_QUESTION)]),
                ANSWER,
            ]
        )
        events = await collect(service, ChatRequest(message=IRON_QUESTION))
        kinds = [k for k, _ in events]
        assert kinds[0] == "route" and kinds[-2:] == ["final", "done"]
        assert events[0][1] == {"intent": "rag", "planned": [SEARCH_TOOL_NAME]}
        assert "tool" not in kinds
        assert "".join(d["text"] for k, d in events if k == "token") == ANSWER

        reference_llm = RecordingChatModel(responses=[ANSWER])
        store = InMemoryKnowledgeStore(CORPUS)
        reference = RagPipeline(
            retrievers={"basic": BasicRetriever(store), "advanced": AdvancedRetriever(store, None)},
            chat_model=reference_llm,
        )
        tokens, final = [], None
        async for item in reference.stream(IRON_QUESTION, "advanced"):
            if isinstance(item, str):
                tokens.append(item)
            else:
                final = item
        assert [d["text"] for k, d in events if k == "token"] == tokens
        final_event = next(d for k, d in events if k == "final")
        assert final_event["citations"] == [c.model_dump(mode="json") for c in final.citations]
        assert final_event["retrieval"] == final.retrieval.model_dump(mode="json")
        assert final_event["disclaimer"] == DISCLAIMER and final_event["tools"] == []

    async def test_tool_events_precede_tokens_and_final_summarises(self) -> None:
        service, llm = make_service(
            [
                AIMessage(
                    content="",
                    tool_calls=[call("calculate_protein_target", age_months=8, weight_kg=8.5)],
                ),
                "She needs about 9.4 g of protein a day.",
            ]
        )
        request = ChatRequest.model_validate({"message": "how much protein?", "child": CHILD})
        events = await collect(service, request)
        kinds = [k for k, _ in events]
        assert kinds.index("tool") < kinds.index("token")
        assert kinds == ["route", "tool", *["token"] * kinds.count("token"), "final", "done"]
        tool = next(d for k, d in events if k == "tool")
        assert tool["status"] == "ok" and tool["used_context"] == ["age_months", "weight_kg"]
        final = next(d for k, d in events if k == "final")
        assert final["intent"] == "tool" and final["retrieval"] is None
        assert final["tools"] == [{"name": "calculate_protein_target", "status": "ok"}]
        assert final["disclaimer"] == DISCLAIMER
        # The answer call uses the tools prompt, not the RAG prompt.
        assert "State every number exactly" in llm.calls[1][0].content

    async def test_hybrid_prompt_carries_context_and_untouched_tool_numbers(self) -> None:
        service, llm = make_service(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        call("calculate_protein_target", age_months=8, weight_kg=8.5),
                        call(SEARCH_TOOL_NAME, query=IRON_QUESTION),
                    ],
                ),
                "answer",
            ]
        )
        request = ChatRequest.model_validate({"message": "iron and protein?", "child": CHILD})
        events = await collect(service, request)
        assert events[0][1]["intent"] == "hybrid"
        prompt = llm.calls[1][1].content
        assert "Infants 7 to 12 months need 11 mg of iron each day" in prompt
        expected = calculate_protein_target(ProteinTargetInput(age_months=8, weight_kg=8.5))
        assert f'"protein_g": {expected.protein_g}' in prompt
        final = next(d for k, d in events if k == "final")
        assert final["citations"][0]["source"] == "Iron Source"
        assert final["retrieval"]["kept"] == 1

    async def test_failing_tool_still_ends_in_done(self) -> None:
        service, _ = make_service(
            [
                AIMessage(content="", tool_calls=[call("lookup_food", food_id="nope")]),
                "We couldn't find that food.",
            ]
        )
        events = await collect(service, ChatRequest(message="what's in nope?"))
        tool = next(d for k, d in events if k == "tool")
        assert tool["status"] == "error" and tool["error"] == copy.unknown_food("nope")
        assert events[-1][0] == "done"
        final = next(d for k, d in events if k == "final")
        assert final["disclaimer"] == DISCLAIMER

    async def test_routing_log_line(self, caplog) -> None:
        service, _ = make_service(
            [
                AIMessage(
                    content="", tool_calls=[call("calculate_bmi", weight_kg=9, height_cm=72)]
                ),
                "ok",
            ]
        )
        with caplog.at_level(logging.INFO, logger="backend.chat.router"):
            await collect(service, ChatRequest(message="bmi?"))
        line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("chat "))
        assert "intent=tool" in line and "calculate_bmi:ok" in line and "latency_ms=" in line

    async def test_answer_collects_the_same_content(self) -> None:
        service, _ = make_service(
            [
                AIMessage(content="", tool_calls=[call(SEARCH_TOOL_NAME, query=IRON_QUESTION)]),
                ANSWER,
            ]
        )
        response = await service.answer(ChatRequest(message=IRON_QUESTION))
        assert response.answer == ANSWER and response.intent == "rag"
        assert response.citations[0].source == "Iron Source" and response.tools == []
        assert response.disclaimer == DISCLAIMER and response.retrieval.kept == 1
