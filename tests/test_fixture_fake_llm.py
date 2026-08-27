"""The recording fake can script tool calls and accept bound tools (Day 5 task 1.3)."""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from tests.fixtures.fake_llm import RecordingChatModel


@tool
def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Toy tool for binding."""
    return weight_kg / (height_cm / 100) ** 2


async def test_scripted_ai_message_with_tool_calls_is_returned_intact() -> None:
    scripted = AIMessage(
        content="",
        tool_calls=[
            {"name": "calculate_bmi", "args": {"weight_kg": 9, "height_cm": 72}, "id": "c1"}
        ],
    )
    llm = RecordingChatModel(responses=[scripted])
    reply = await llm.ainvoke([HumanMessage(content="bmi?")])
    assert reply.tool_calls == scripted.tool_calls
    assert reply.content == ""
    assert len(llm.calls) == 1


def test_bind_tools_returns_self_and_records_names() -> None:
    llm = RecordingChatModel(responses=["hi"])
    bound = llm.bind_tools([calculate_bmi])
    assert bound is llm
    assert llm.bound_tools == ["calculate_bmi"]


def test_string_responses_still_stream_word_by_word() -> None:
    llm = RecordingChatModel(responses=["one two three"])
    chunks = [c.content for c in llm.stream([HumanMessage(content="x")]) if c.content]
    assert chunks == ["one ", "two ", "three"]


def test_ai_message_response_streams_its_text() -> None:
    llm = RecordingChatModel(responses=[AIMessage(content="a b")])
    chunks = [c.content for c in llm.stream([HumanMessage(content="x")]) if c.content]
    assert chunks == ["a ", "b"]
