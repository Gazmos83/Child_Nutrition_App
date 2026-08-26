"""POST /api/ask contract (Day 3 task 6.2; ask-api spec)."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.api.ask import get_rag_pipeline
from backend.core.config import get_rag_settings
from backend.db.knowledge_store import Document
from backend.main import create_app
from backend.rag.llm import reset_pipeline_cache
from backend.rag.pipeline import RagPipeline
from backend.rag.prompts import DISCLAIMER, NO_ANSWER_MESSAGE
from backend.rag.retrievers import AdvancedRetriever, BasicRetriever
from tests.fixtures.fake_llm import RecordingChatModel
from tests.fixtures.memory_store import InMemoryKnowledgeStore

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


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
def llm() -> RecordingChatModel:
    return RecordingChatModel(responses=[ANSWER, ANSWER, ANSWER])


@pytest.fixture
def client(llm: RecordingChatModel) -> TestClient:
    store = InMemoryKnowledgeStore(CORPUS)
    pipeline = RagPipeline(
        retrievers={"basic": BasicRetriever(store), "advanced": AdvancedRetriever(store, None)},
        chat_model=llm,
    )
    app = create_app()
    app.dependency_overrides[get_rag_pipeline] = lambda: pipeline
    with TestClient(app) as c:
        yield c


class TestValidation:
    def test_blank_question_is_422_before_any_work(self, client: TestClient, llm) -> None:
        r = client.post("/api/ask", json={"question": "   "})
        assert r.status_code == 422
        assert llm.calls == []

    def test_missing_question_is_422(self, client: TestClient) -> None:
        assert client.post("/api/ask", json={}).status_code == 422

    def test_over_long_question_is_422(self, client: TestClient) -> None:
        assert client.post("/api/ask", json={"question": "x" * 2001}).status_code == 422

    def test_unknown_strategy_is_422(self, client: TestClient) -> None:
        r = client.post("/api/ask", json={"question": "iron?", "strategy": "hybrid"})
        assert r.status_code == 422

    def test_unknown_field_is_422(self, client: TestClient) -> None:
        r = client.post("/api/ask", json={"question": "iron?", "user_id": "abc"})
        assert r.status_code == 422


class TestJsonResponse:
    def test_shape_is_exactly_the_five_fields(self, client: TestClient) -> None:
        r = client.post(
            "/api/ask", json={"question": "how much iron do infants need each day", "stream": False}
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"answer", "citations", "disclaimer", "strategy", "retrieval"}
        assert body["answer"] == ANSWER
        assert body["disclaimer"] == DISCLAIMER
        assert body["strategy"] == "advanced"  # default
        assert body["citations"][0]["source"] == "Iron Source"
        assert body["citations"][0]["year"] == 2010
        assert body["citations"][0]["index"] == 1
        assert set(body["retrieval"]) >= {
            "strategy",
            "queries",
            "filters",
            "filter_dropped",
            "retrieved",
            "kept",
        }
        assert body["retrieval"]["filters"] == {"age_min_months": 0, "age_max_months": 12}

    def test_basic_strategy_is_reported(self, client: TestClient) -> None:
        body = client.post(
            "/api/ask", json={"question": "iron for infants", "strategy": "basic", "stream": False}
        ).json()
        assert body["strategy"] == "basic" and body["retrieval"]["queries"] == ["iron for infants"]

    def test_no_answer_json(self, client: TestClient, llm) -> None:
        body = client.post(
            "/api/ask", json={"question": "What is the capital of France?", "stream": False}
        ).json()
        assert body["answer"] == NO_ANSWER_MESSAGE and body["citations"] == []
        assert body["disclaimer"] == DISCLAIMER and llm.calls == []


class TestStreaming:
    def test_default_is_sse_with_ordered_events(self, client: TestClient) -> None:
        r = client.post("/api/ask", json={"question": "how much iron do infants need each day"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(r.text)
        kinds = [k for k, _ in events]
        assert kinds[-2:] == ["citations", "done"]
        assert kinds.count("citations") == 1 and kinds.count("done") == 1
        assert all(k == "token" for k in kinds[:-2]) and len(kinds) > 3
        assert "".join(d["text"] for k, d in events if k == "token") == ANSWER
        citations = next(d for k, d in events if k == "citations")
        assert citations["citations"][0]["source"] == "Iron Source"
        assert citations["disclaimer"] == DISCLAIMER
        assert citations["retrieval"]["kept"] == 1

    def test_no_answer_is_streamed_with_empty_citations(self, client: TestClient) -> None:
        events = parse_sse(
            client.post("/api/ask", json={"question": "What is the capital of France?"}).text
        )
        tokens = [d["text"] for k, d in events if k == "token"]
        assert tokens == [NO_ANSWER_MESSAGE]
        assert next(d for k, d in events if k == "citations")["citations"] == []
        assert events[-1][0] == "done"

    def test_mid_stream_failure_ends_with_error_and_no_done(self, llm) -> None:
        llm.responses = ["one two three four five"]
        llm.fail_with, llm.fail_after_tokens = "upstream", 2
        store = InMemoryKnowledgeStore(CORPUS)
        pipeline = RagPipeline(retrievers={"basic": BasicRetriever(store)}, chat_model=llm)
        app = create_app()
        app.dependency_overrides[get_rag_pipeline] = lambda: pipeline
        with TestClient(app) as c:
            events = parse_sse(
                c.post("/api/ask", json={"question": "iron infants", "strategy": "basic"}).text
            )
        kinds = [k for k, _ in events]
        assert kinds == ["token", "token", "error"]
        assert "done" not in kinds
        assert "message" in events[-1][1]


class TestUnconfigured:
    def test_missing_key_is_503_naming_the_setting(self, monkeypatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setattr(
            "backend.core.config.RAGSettings.model_config",
            {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"},
        )
        get_rag_settings.cache_clear()
        reset_pipeline_cache()
        try:
            with TestClient(create_app()) as c:
                r = c.post("/api/ask", json={"question": "iron?", "stream": False})
                assert r.status_code == 503
                assert "OPENROUTER_API_KEY" in r.json()["detail"]
                assert c.get("/health").status_code == 200
        finally:
            get_rag_settings.cache_clear()
            reset_pipeline_cache()

    def test_missing_knowledge_base_is_503(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setenv("MILVUS_DB_PATH", str(tmp_path / "absent.db"))
        monkeypatch.setattr(
            "backend.core.config.RAGSettings.model_config",
            {"env_file": None, "env_file_encoding": "utf-8", "extra": "ignore"},
        )
        get_rag_settings.cache_clear()
        reset_pipeline_cache()
        try:
            with TestClient(create_app()) as c:
                r = c.post(
                    "/api/ask", json={"question": "iron?", "strategy": "basic", "stream": False}
                )
            assert r.status_code == 503
            assert "scripts/ingest.py" in r.json()["detail"]
        finally:
            get_rag_settings.cache_clear()
            reset_pipeline_cache()
