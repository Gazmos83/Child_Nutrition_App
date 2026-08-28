"""``/api/children`` and the chat's authority seam against PostgreSQL.

This is hard rule 9's evidence (user-account spec, "Ownership is the authorization
boundary"; Day 1 task 7.10): an owner sees exactly their own records, a non-owner gets the
same answer as for a record that does not exist, and no session means no data.
"""

import uuid

import pytest
from httpx import AsyncClient

from backend.api.chat import get_service, resolve_chat_request
from backend.models import User
from backend.schemas.chat import ChatRequest
from tests.conftest import sign_in

pytestmark = pytest.mark.db

CHILD = {"age_months": 8, "weight_kg": 8.5, "sex": "female", "allergies": ["peanut", "milk"]}
FORMULA = {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 150}
NOWHERE = uuid.UUID("0198f0a0-0000-7000-8000-000000000001")


async def create_child(client: AsyncClient, **overrides) -> dict:
    response = await client.post("/api/children", json={**CHILD, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def log_feed(client: AsyncClient, child_id: str, **overrides) -> dict:
    body = {**FORMULA, **overrides}
    response = await client.post(f"/api/children/{child_id}/feedings", json=body)
    assert response.status_code == 201, response.text
    return response.json()


class TestProfiles:
    async def test_create_and_read_back(self, auth_client: AsyncClient) -> None:
        created = await create_child(auth_client, doctors_note="  limit to 650 kcal/day ")
        assert created["age_months"] == 8 and created["weight_kg"] == 8.5
        assert created["allergies"] == ["milk", "peanut"]  # sorted, deduplicated
        assert created["doctors_note"] == "  limit to 650 kcal/day "
        assert created["doctors_note_recorded_at"] is not None
        assert created["activity_level"] == "low_active" and created["height_cm"] is None

        listed = await auth_client.get("/api/children")
        assert listed.status_code == 200 and [c["id"] for c in listed.json()] == [created["id"]]
        one = await auth_client.get(f"/api/children/{created['id']}")
        assert one.status_code == 200 and one.json() == created

    async def test_replace_updates_every_field_and_dates_a_changed_note(
        self, auth_client: AsyncClient
    ) -> None:
        created = await create_child(auth_client)
        replaced = await auth_client.put(
            f"/api/children/{created['id']}",
            json={**CHILD, "weight_kg": 9.1, "allergies": [], "doctors_note": "no honey"},
        )
        assert replaced.status_code == 200
        body = replaced.json()
        assert body["weight_kg"] == 9.1 and body["allergies"] == []
        assert body["doctors_note"] == "no honey" and body["doctors_note_recorded_at"]

        cleared = await auth_client.put(
            f"/api/children/{created['id']}", json={**CHILD, "doctors_note": "   "}
        )
        assert cleared.json()["doctors_note"] is None
        assert cleared.json()["doctors_note_recorded_at"] is None

    async def test_delete_removes_the_profile_and_its_log(self, auth_client: AsyncClient) -> None:
        created = await create_child(auth_client)
        await auth_client.post(f"/api/children/{created['id']}/feedings", json=FORMULA)
        assert (await auth_client.delete(f"/api/children/{created['id']}")).status_code == 204
        assert (await auth_client.get(f"/api/children/{created['id']}")).status_code == 404
        assert (await auth_client.get("/api/children")).json() == []

    @pytest.mark.parametrize(
        "overrides",
        [
            {"age_months": 61},
            {"weight_kg": 0},
            {"allergies": ["gluten"]},
            {"diet_preference": "keto"},
            {"age_months": 40},  # height required from 36 months
            {"nickname": "bean"},
            {"activity_level": "olympic"},
        ],
    )
    async def test_invalid_profile_is_422(self, auth_client: AsyncClient, overrides) -> None:
        response = await auth_client.post("/api/children", json={**CHILD, **overrides})
        assert response.status_code == 422


class TestOwnership:
    """The scenarios written on Day 1 for exactly this day."""

    async def test_owner_lists_only_their_own(
        self, api_client: AsyncClient, user: User, other_user: User
    ) -> None:
        sign_in(api_client, user)
        mine = await create_child(api_client)
        sign_in(api_client, other_user)
        theirs = await create_child(api_client, age_months=20, sex="male")

        sign_in(api_client, user)
        assert [c["id"] for c in (await api_client.get("/api/children")).json()] == [mine["id"]]
        sign_in(api_client, other_user)
        assert [c["id"] for c in (await api_client.get("/api/children")).json()] == [theirs["id"]]

    async def test_non_owner_gets_the_same_404_as_nonexistent(
        self, api_client: AsyncClient, user: User, other_user: User
    ) -> None:
        sign_in(api_client, user)
        mine = await create_child(api_client)
        fed = (await api_client.post(f"/api/children/{mine['id']}/feedings", json=FORMULA)).json()

        sign_in(api_client, other_user)
        for method, path, body in [
            ("GET", f"/api/children/{mine['id']}", None),
            ("PUT", f"/api/children/{mine['id']}", CHILD),
            ("DELETE", f"/api/children/{mine['id']}", None),
            ("GET", f"/api/children/{mine['id']}/feedings", None),
            ("POST", f"/api/children/{mine['id']}/feedings", FORMULA),
            ("DELETE", f"/api/children/{mine['id']}/feedings/{fed['entry']['id']}", None),
        ]:
            as_non_owner = await api_client.request(method, path, json=body)
            as_nonexistent = await api_client.request(
                method, path.replace(mine["id"], str(NOWHERE)), json=body
            )
            assert as_non_owner.status_code == 404, (method, path)
            assert as_non_owner.status_code == as_nonexistent.status_code
            assert as_non_owner.content == as_nonexistent.content, (method, path)

        # Nothing changed for the owner.
        sign_in(api_client, user)
        assert (await api_client.get(f"/api/children/{mine['id']}")).status_code == 200
        assert len((await api_client.get(f"/api/children/{mine['id']}/feedings")).json()) == 1

    async def test_unauthenticated_gets_no_record_data(
        self, api_client: AsyncClient, user: User
    ) -> None:
        sign_in(api_client, user)
        mine = await create_child(api_client)
        api_client.cookies.clear()
        for path in (
            "/api/children",
            f"/api/children/{mine['id']}",
            f"/api/children/{mine['id']}/feedings",
        ):
            response = await api_client.get(path)
            assert response.status_code == 401
            assert response.json() == {"detail": "Sign in to continue"}


class TestFeedingLog:
    async def test_log_read_back_priced(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        response = await auth_client.post(f"/api/children/{child['id']}/feedings", json=FORMULA)
        assert response.status_code == 201
        logged = response.json()
        assert logged["food_id"] == "infant_formula_iron_fortified"
        assert logged["nutrients"]["calories"] == 100.5
        uuid.UUID(logged["entry"]["id"])

        listed = await auth_client.get(f"/api/children/{child['id']}/feedings")
        assert listed.status_code == 200
        assert [e["entry"]["id"] for e in listed.json()] == [logged["entry"]["id"]]
        assert listed.json()[0]["nutrients"]["calories"] == 100.5

    async def test_reposting_the_same_id_is_idempotent(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        first = await log_feed(auth_client, child["id"])
        again = await auth_client.post(f"/api/children/{child['id']}/feedings", json=first["entry"])
        assert again.status_code == 201 and again.json()["entry"]["id"] == first["entry"]["id"]
        assert len((await auth_client.get(f"/api/children/{child['id']}/feedings")).json()) == 1

    async def test_breastmilk_without_quantity_is_stored(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        response = await auth_client.post(
            f"/api/children/{child['id']}/feedings",
            json={"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "breastmilk"},
        )
        assert response.status_code == 201
        assert response.json()["quantified"] is False

    @pytest.mark.parametrize(
        ("body", "fragment"),
        [
            ({"feeding_type": "solid", "food_id": "dragonfruit", "unit": "g"}, "dragonfruit"),
            ({"feeding_type": "solid", "food_id": "avocado", "unit": "ml"}, "measured in g"),
        ],
    )
    async def test_table_contradictions_are_422(self, auth_client: AsyncClient, body, fragment):
        child = await create_child(auth_client)
        response = await auth_client.post(
            f"/api/children/{child['id']}/feedings", json={**FORMULA, **body}
        )
        assert response.status_code == 422 and fragment in response.json()["detail"]

    async def test_shape_errors_are_422_before_the_table(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        for body in (
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula"},  # no quantity
            {"fed_at": "2026-08-27T09:00:00", "feeding_type": "breastmilk"},  # naive time
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "snack", "quantity": 1},
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "water", "quantity": 50, "x": 1},
            {**FORMULA, "id": "not-a-uuid"},
        ):
            response = await auth_client.post(f"/api/children/{child['id']}/feedings", json=body)
            assert response.status_code == 422, body
        assert (await auth_client.get(f"/api/children/{child['id']}/feedings")).json() == []

    async def test_replay_with_a_different_body_returns_the_stored_row(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(auth_client)
        first = await log_feed(auth_client, child["id"])
        replay = await auth_client.post(
            f"/api/children/{child['id']}/feedings",
            json={**first["entry"], "quantity": 999},
        )
        assert replay.status_code == 201 and replay.json()["entry"]["quantity"] == 150

    async def test_delete_removes_one_entry(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        kept = await log_feed(auth_client, child["id"])
        gone = await log_feed(auth_client, child["id"], fed_at="2026-08-27T12:00:00Z")
        response = await auth_client.delete(
            f"/api/children/{child['id']}/feedings/{gone['entry']['id']}"
        )
        assert response.status_code == 204
        remaining = (await auth_client.get(f"/api/children/{child['id']}/feedings")).json()
        assert [e["entry"]["id"] for e in remaining] == [kept["entry"]["id"]]


class TestChatAuthoritySeam:
    """``POST /api/chat`` reads the child and the log from the account, never the body."""

    @pytest.fixture
    def captured(self, api_client: AsyncClient) -> list[ChatRequest]:
        """Replace the chat service with one that records the resolved request."""
        seen: list[ChatRequest] = []

        class Recorder:
            async def answer(self, request: ChatRequest):
                seen.append(request)
                from backend.schemas.chat import ChatResponse

                return ChatResponse(
                    answer="ok",
                    intent="tool",
                    tools=[],
                    citations=[],
                    retrieval=None,
                    disclaimer="d",
                )

        app = api_client._transport.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_service] = lambda: Recorder()
        return seen

    async def test_child_and_log_come_from_the_rows(
        self, auth_client: AsyncClient, captured: list[ChatRequest]
    ) -> None:
        child = await create_child(auth_client)
        await auth_client.post(f"/api/children/{child['id']}/feedings", json=FORMULA)
        response = await auth_client.post(
            "/api/chat", json={"message": "enough iron?", "stream": False}
        )
        assert response.status_code == 200, response.text
        [request] = captured
        assert request.child is not None
        assert request.child.age_months == 8 and request.child.allergies == {"peanut", "milk"}
        assert [e.feeding_type for e in request.feeding_log] == ["formula"]
        assert request.feeding_log[0].quantity == 150

    async def test_body_cannot_carry_a_child(self, auth_client: AsyncClient, captured) -> None:
        response = await auth_client.post(
            "/api/chat", json={"message": "hi", "child": CHILD, "stream": False}
        )
        assert response.status_code == 422 and captured == []

    async def test_no_child_yet_proceeds_without_context(
        self, auth_client: AsyncClient, captured: list[ChatRequest]
    ) -> None:
        response = await auth_client.post("/api/chat", json={"message": "hi", "stream": False})
        assert response.status_code == 200
        assert captured[0].child is None and captured[0].feeding_log == []

    async def test_several_children_require_child_id(
        self, auth_client: AsyncClient, captured: list[ChatRequest]
    ) -> None:
        first = await create_child(auth_client)
        await create_child(auth_client, age_months=30, sex="male")
        ambiguous = await auth_client.post("/api/chat", json={"message": "hi", "stream": False})
        assert ambiguous.status_code == 422 and "child_id" in ambiguous.json()["detail"]
        explicit = await auth_client.post(
            "/api/chat", json={"message": "hi", "child_id": first["id"], "stream": False}
        )
        assert explicit.status_code == 200 and captured[0].child.age_months == 8

    async def test_unowned_child_id_is_404(
        self, api_client: AsyncClient, user: User, other_user: User, captured
    ) -> None:
        sign_in(api_client, other_user)
        theirs = await create_child(api_client)
        sign_in(api_client, user)
        response = await api_client.post(
            "/api/chat", json={"message": "hi", "child_id": theirs["id"], "stream": False}
        )
        nonexistent = await api_client.post(
            "/api/chat", json={"message": "hi", "child_id": str(NOWHERE), "stream": False}
        )
        assert response.status_code == nonexistent.status_code == 404
        assert response.content == nonexistent.content and captured == []

    async def test_unauthenticated_chat_is_401(self, api_client: AsyncClient, captured) -> None:
        response = await api_client.post("/api/chat", json={"message": "hi", "stream": False})
        assert response.status_code == 401 and captured == []


# resolve_chat_request is exercised through the routes above; the import documents that.
_ = resolve_chat_request
