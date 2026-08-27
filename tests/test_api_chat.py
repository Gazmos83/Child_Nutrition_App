"""POST /api/chat contract (Day 5 task 4.2; chat-api spec)."""

import json

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from backend.api.chat import get_service
from backend.chat import copy
from backend.chat.router import SEARCH_TOOL_NAME
from backend.chat.service import ChatService
from backend.db.knowledge_store import Document
from backend.main import create_app
from backend.rag.pipeline import RagPipeline
from backend.rag.prompts import DISCLAIMER
from backend.rag.retrievers import AdvancedRetriever, BasicRetriever
from backend.tools.langchain_tools import build_tools
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


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def make_client(llm: RecordingChatModel) -> TestClient:
    store = InMemoryKnowledgeStore(CORPUS)
    pipeline = RagPipeline(
        retrievers={"basic": BasicRetriever(store), "advanced": AdvancedRetriever(store, None)},
        chat_model=llm,
    )
    service = ChatService(pipeline, llm, build_tools(None))
    app = create_app()
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def llm() -> RecordingChatModel:
    return RecordingChatModel(responses=[])


@pytest.fixture
def client(llm: RecordingChatModel) -> TestClient:
    with make_client(llm) as c:
        yield c


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"message": "   "},
            {"message": "hi", "user_id": "abc"},
            {"message": "hi", "history": [{"role": "user", "content": "q"}] * 13},
            {"message": "hi", "child": {**CHILD, "age_months": 61}},
            {"message": "hi", "child": {**CHILD, "allergies": ["gluten"]}},
        ],
    )
    def test_422_before_any_work(self, client: TestClient, llm, body: dict) -> None:
        assert client.post("/api/chat", json=body).status_code == 422
        assert llm.calls == []


class TestUnavailable:
    def test_503_when_service_cannot_be_built(self) -> None:
        app = create_app()

        def unconfigured() -> ChatService:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="OPENROUTER_API_KEY")

        app.dependency_overrides[get_service] = unconfigured
        with TestClient(app) as c:
            r = c.post("/api/chat", json={"message": "hi"})
        assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]

    def test_503_when_answer_raises_runtime_error(self, monkeypatch) -> None:
        llm = RecordingChatModel(responses=[])
        with make_client(llm) as c:
            service = c.app.dependency_overrides[get_service]()

            async def failing(request):
                raise RuntimeError("knowledge base is empty")

            monkeypatch.setattr(service, "answer", failing)
            r = c.post("/api/chat", json={"message": "hi", "stream": False})
        assert r.status_code == 503 and "knowledge base" in r.json()["detail"]


class TestStreaming:
    def test_tool_answer_event_order(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(
                content="",
                tool_calls=[call("calculate_protein_target", age_months=8, weight_kg=8.5)],
            ),
            "About 9.4 g a day.",
        ]
        r = client.post("/api/chat", json={"message": "protein?", "child": CHILD})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(r.text)
        kinds = [k for k, _ in events]
        assert kinds[0] == "route" and kinds[1] == "tool" and kinds[-2:] == ["final", "done"]
        assert all(k == "token" for k in kinds[2:-2]) and kinds.count("token") >= 1
        assert kinds.index("tool") < kinds.index("token")
        assert events[0][1] == {"intent": "tool", "planned": ["calculate_protein_target"]}
        assert events[1][1]["status"] == "ok" and "age_months" in events[1][1]["used_context"]
        final = events[-2][1]
        assert set(final) == {"citations", "retrieval", "disclaimer", "intent", "tools"}
        assert final["disclaimer"] == DISCLAIMER

    def test_rag_answer_carries_citations(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(content="", tool_calls=[call(SEARCH_TOOL_NAME, query=IRON_QUESTION)]),
            ANSWER,
        ]
        events = parse_sse(client.post("/api/chat", json={"message": IRON_QUESTION}).text)
        assert "".join(d["text"] for k, d in events if k == "token") == ANSWER
        final = next(d for k, d in events if k == "final")
        assert final["citations"][0]["source"] == "Iron Source"
        assert final["citations"][0]["year"] == 2010
        assert final["intent"] == "rag" and final["retrieval"]["kept"] == 1

    def test_disclaimer_when_every_tool_fails(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(content="", tool_calls=[call("lookup_food", food_id="nope")]),
            "We couldn't find that one.",
        ]
        events = parse_sse(client.post("/api/chat", json={"message": "nope?"}).text)
        tool = next(d for k, d in events if k == "tool")
        assert tool["status"] == "error" and tool["error"] == copy.unknown_food("nope")
        final = next(d for k, d in events if k == "final")
        assert final["disclaimer"] == DISCLAIMER and final["tools"][0]["status"] == "error"
        assert events[-1][0] == "done"

    def test_mid_stream_failure_ends_with_error_event(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(content="", tool_calls=[call("calculate_bmi", weight_kg=9, height_cm=72)]),
            "one two three four",
        ]
        llm.fail_with = "provider dropped"
        llm.fail_after_tokens = 2
        events = parse_sse(client.post("/api/chat", json={"message": "bmi?"}).text)
        kinds = [k for k, _ in events]
        assert kinds.count("error") == 1 and "done" not in kinds
        assert kinds[-1] == "error"
        assert events[-1][1] == {"message": copy.STREAM_FAILED}
        assert "provider dropped" not in json.dumps(events)


class TestJsonResponse:
    def test_shape_is_exactly_the_six_fields(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(content="", tool_calls=[call(SEARCH_TOOL_NAME, query=IRON_QUESTION)]),
            ANSWER,
        ]
        r = client.post("/api/chat", json={"message": IRON_QUESTION, "stream": False})
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"answer", "intent", "tools", "citations", "retrieval", "disclaimer"}
        assert body["answer"] == ANSWER and body["intent"] == "rag" and body["tools"] == []
        assert body["citations"][0]["index"] == 1 and body["disclaimer"] == DISCLAIMER

    def test_tool_json_includes_activities(self, client: TestClient, llm) -> None:
        llm.responses[:] = [
            AIMessage(content="", tool_calls=[call("calculate_bmi", weight_kg=9, height_cm=72)]),
            "BMI is 17.36.",
        ]
        body = client.post("/api/chat", json={"message": "bmi?", "stream": False}).json()
        assert body["intent"] == "tool" and body["retrieval"] is None
        assert body["tools"][0]["name"] == "calculate_bmi"
        assert body["tools"][0]["result"]["bmi"] == 17.36
