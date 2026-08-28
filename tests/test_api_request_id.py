"""Request correlation, access records, and the last-resort 500 (observability spec).

Offline tests drive the app with ``TestClient`` (records are captured inside the app, where
the request context lives). The ``db`` tests at the end check identity correlation through
the real session and profile rows.
"""

import json
import logging
import uuid

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from httpx import AsyncClient
from langchain_core.messages import AIMessage

from backend.api.chat import get_service
from backend.chat import copy
from backend.main import create_app
from backend.models import User
from tests.conftest import sign_in
from tests.test_api_chat import _resolved_from_body, make_client, parse_sse

ACCESS = "backend.api.access"


def access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == ACCESS]


class TestRequestId:
    def test_header_on_every_response(self, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger=ACCESS)
        with TestClient(create_app()) as client:
            for path, expected in (("/health", 200), ("/api/foods", 200), ("/api/auth/me", None)):
                response = client.get(path)
                if expected is not None:
                    assert response.status_code == expected
                uuid.UUID(response.headers["x-request-id"])
        ids = {r.request_id for r in access_records(caplog)}
        assert len(ids) == 3, "one distinct id per request"

    def test_incoming_uuid_is_honoured_and_junk_is_replaced(self) -> None:
        with TestClient(create_app()) as client:
            given = str(uuid.uuid7())
            echoed = client.get("/health", headers={"X-Request-ID": given}).headers["x-request-id"]
            assert echoed == given
            replaced = client.get("/health", headers={"X-Request-ID": "not-a-uuid"}).headers[
                "x-request-id"
            ]
            assert replaced != "not-a-uuid"
            uuid.UUID(replaced)

    def test_one_access_record_per_request_with_fields(self, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger=ACCESS)
        with TestClient(create_app()) as client:
            client.get("/api/foods")
            client.get("/api/auth/me")
        records = access_records(caplog)
        assert [(r.method, r.route, r.status) for r in records] == [
            ("GET", "/api/foods", 200),
            ("GET", "/api/auth/me", 401),
        ]
        for record in records:
            assert isinstance(record.latency_ms, int) and record.latency_ms >= 0
            assert record.user_id is None
            assert record.levelno == logging.INFO
            assert record.request_id

    def test_health_is_quiet(self, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger=ACCESS)
        with TestClient(create_app()) as client:
            client.get("/health")
        [record] = access_records(caplog)
        assert record.levelno == logging.DEBUG and record.route == "/health"

    def test_route_template_not_raw_path(self, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger=ACCESS)
        with TestClient(create_app()) as client:
            client.get(f"/api/children/{uuid.uuid7()}")
        [record] = access_records(caplog)
        assert record.route == "/api/children/{child_id}" and record.status == 401

    def test_streamed_chat_carries_the_id_throughout(self, caplog) -> None:
        caplog.set_level(logging.DEBUG)
        from tests.fixtures.fake_llm import RecordingChatModel

        bmi_call = {
            "name": "calculate_bmi",
            "args": {"weight_kg": 9, "height_cm": 72},
            "id": "c1",
            "type": "tool_call",
        }
        llm = RecordingChatModel(
            responses=[AIMessage(content="", tool_calls=[bmi_call]), "BMI is 17.36."]
        )
        with make_client(llm) as client:
            response = client.post("/api/chat", json={"message": "bmi?"})
        request_id = response.headers["x-request-id"]
        kinds = [k for k, _ in parse_sse(response.text)]
        assert kinds[-1] == "done"
        in_request = [r for r in caplog.records if r.name.startswith("backend.") and r.request_id]
        assert {r.request_id for r in in_request} == {request_id}
        names = {r.name for r in in_request}
        assert {"backend.chat.tools", "backend.chat.router", ACCESS} <= names
        [access] = access_records(caplog)
        assert access.route == "/api/chat" and access.status == 200


class TestUnhandledErrors:
    def _app_with_failing_route(self):
        app = create_app()
        router = APIRouter()

        @router.get("/boom")
        async def boom() -> None:
            raise RuntimeError("secret detail that must not leak")

        app.include_router(router)
        return app

    def test_500_body_is_fixed_message_and_request_id(self, caplog) -> None:
        caplog.set_level(logging.DEBUG)
        with TestClient(self._app_with_failing_route(), raise_server_exceptions=False) as client:
            response = client.get("/boom")
        assert response.status_code == 500
        body = response.json()
        assert set(body) == {"detail", "request_id"}
        assert body["detail"] == copy.SERVER_ERROR
        assert body["request_id"] == response.headers["x-request-id"]
        assert "secret detail" not in response.text and "Traceback" not in response.text

        errors = [r for r in caplog.records if r.name == "backend.api.errors"]
        assert len(errors) == 1
        [error] = errors
        assert error.levelno == logging.ERROR and error.request_id == body["request_id"]
        assert error.exc_info and "secret detail that must not leak" in str(error.exc_info[1])
        [access] = access_records(caplog)
        assert access.status == 500 and access.route == "/boom"

    def test_http_exceptions_are_not_unhandled_errors(self, caplog) -> None:
        caplog.set_level(logging.DEBUG)
        with TestClient(create_app()) as client:
            response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert not [r for r in caplog.records if r.name == "backend.api.errors"]


class TestIdentityCorrelation:
    pytestmark = pytest.mark.db

    @pytest.mark.db
    async def test_access_record_carries_the_account_id(
        self, auth_client: AsyncClient, user: User, caplog
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=ACCESS)
        response = await auth_client.get("/api/children")
        assert response.status_code == 200
        [record] = access_records(caplog)
        assert record.user_id == str(user.id) and record.route == "/api/children"
        assert record.request_id == response.headers["x-request-id"]

    @pytest.mark.db
    async def test_records_for_a_chat_turn_share_request_account_and_child(
        self, api_client: AsyncClient, user: User, caplog
    ) -> None:
        """Audit, retrieval, routing, tool, and access records all correlate to the same
        request, account, and stored child -- with the audit message text unchanged."""
        from tests.fixtures.fake_llm import RecordingChatModel
        from tests.test_api_children import create_child

        sign_in(api_client, user)
        child = await create_child(api_client)
        await api_client.post(
            f"/api/children/{child['id']}/feedings",
            json={"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 150},
        )
        llm = RecordingChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": name, "args": {}, "id": f"c{i}", "type": "tool_call"}
                        for i, name in enumerate(("generate_meal_plan", "detect_nutrient_gaps"))
                    ],
                ),
                "Here is a day of meals.",
            ]
        )
        from backend.chat.service import ChatService
        from backend.tools.langchain_tools import build_tools

        app = api_client._transport.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_service] = lambda: ChatService(None, llm, build_tools(llm))
        caplog.set_level(logging.DEBUG)
        response = await api_client.post(
            "/api/chat", json={"message": "plan today", "stream": False}
        )
        assert response.status_code == 200, response.text
        request_id = response.headers["x-request-id"]

        by_name = {}
        for record in caplog.records:
            if record.request_id == request_id:
                by_name.setdefault(record.name, []).append(record)
        expected = {"backend.tools.audit", "backend.chat.tools", "backend.chat.router", ACCESS}
        assert expected <= set(by_name)
        for records in by_name.values():
            for record in records:
                assert record.user_id == str(user.id)
                assert record.child_profile_id == child["id"]
        audits = [r.getMessage() for r in by_name["backend.tools.audit"]]
        assert any(m.startswith("meal_plan_audit ") for m in audits)
        assert any(m.startswith("nutrient_gaps_audit ") for m in audits)
        for message in audits:
            json.loads(message.split(" ", 1)[1])  # the JSON payload is still the whole message
        assert "plan today" not in "\n".join(r.getMessage() for r in caplog.records)


# The offline chat client overrides the seam; keep the import used.
_ = _resolved_from_body
