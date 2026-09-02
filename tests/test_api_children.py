"""``/api/children`` and the chat's authority seam against PostgreSQL.

This is hard rule 9's evidence (user-account spec, "Ownership is the authorization
boundary"; Day 1 task 7.10): an owner sees exactly their own records, a non-owner gets the
same answer as for a record that does not exist, and no session means no data.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.chat import get_service, resolve_chat_request
from backend.models import ChildProfile, User
from backend.models.enums import Sex
from backend.nutrition.age import birth_date_for, today
from backend.nutrition.growth import GrowthIndicator, get_growth_table
from backend.schemas.chat import ChatRequest
from backend.schemas.child import AGE_OUT_OF_RANGE_DETAIL
from tests.conftest import sign_in

pytestmark = pytest.mark.db


def born(months: int) -> str:
    """A date of birth that reads as exactly ``months`` completed months today."""
    return birth_date_for(months, today()).isoformat()


CHILD = {"birth_date": born(8), "weight_kg": 8.5, "sex": "female", "allergies": ["peanut", "milk"]}
FORMULA = {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 150}
MEASUREMENT = {"measured_on": today().isoformat(), "weight_kg": 8.7, "height_cm": 70}
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


async def measure(client: AsyncClient, child_id: str, **overrides) -> dict:
    body = {**MEASUREMENT, **overrides}
    response = await client.post(f"/api/children/{child_id}/growth", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def growth_list(client: AsyncClient, child_id: str) -> list[dict]:
    response = await client.get(f"/api/children/{child_id}/growth")
    assert response.status_code == 200, response.text
    return response.json()


async def profile_of(client: AsyncClient, child_id: str) -> dict:
    response = await client.get(f"/api/children/{child_id}")
    assert response.status_code == 200, response.text
    return response.json()


class TestProfiles:
    async def test_create_and_read_back(self, auth_client: AsyncClient) -> None:
        created = await create_child(
            auth_client, notes=[{"kind": "doctor", "text": "  limit to 650 kcal/day "}]
        )
        assert created["age_months"] == 8 and created["weight_kg"] == 8.5
        assert created["birth_date"] == CHILD["birth_date"]  # stored; the age is derived
        assert created["allergies"] == ["milk", "peanut"]  # sorted, deduplicated
        [row] = created["notes"]
        assert row["kind"] == "doctor" and row["text"] == "limit to 650 kcal/day"
        assert row["recorded_at"] is not None and uuid.UUID(row["id"])
        assert created["activity_level"] == "low_active" and created["height_cm"] is None

        listed = await auth_client.get("/api/children")
        assert listed.status_code == 200 and [c["id"] for c in listed.json()] == [created["id"]]
        one = await auth_client.get(f"/api/children/{created['id']}")
        assert one.status_code == 200 and one.json() == created

    async def test_replace_updates_every_field_and_dates_a_changed_note(
        self, auth_client: AsyncClient
    ) -> None:
        honey = {"kind": "doctor", "text": "no honey"}
        pork = {"kind": "preference", "text": "no pork"}
        created = await create_child(auth_client, notes=[honey])
        [kept_before] = created["notes"]
        replaced = await auth_client.put(
            f"/api/children/{created['id']}",
            json={**CHILD, "weight_kg": 9.1, "allergies": [], "notes": [pork, honey]},
        )
        assert replaced.status_code == 200
        body = replaced.json()
        assert body["weight_kg"] == 9.1 and body["allergies"] == []
        assert [(n["kind"], n["text"]) for n in body["notes"]] == [
            ("preference", "no pork"),
            ("doctor", "no honey"),
        ]
        # The unchanged row keeps its identity and date in its new position; the new row is new.
        kept_after = next(n for n in body["notes"] if n["text"] == "no honey")
        assert kept_after["id"] == kept_before["id"]
        assert kept_after["recorded_at"] == kept_before["recorded_at"]
        assert next(n for n in body["notes"] if n["text"] == "no pork")["id"] != kept_before["id"]

        changed = await auth_client.put(
            f"/api/children/{created['id']}",
            json={**CHILD, "notes": [{"kind": "doctor", "text": "no honey at all"}]},
        )
        [row] = changed.json()["notes"]
        assert row["id"] != kept_before["id"]  # a changed text is a new row

        cleared = await auth_client.put(
            f"/api/children/{created['id']}", json={**CHILD, "notes": []}
        )
        assert cleared.json()["notes"] == []

    async def test_delete_removes_the_profile_and_its_log(self, auth_client: AsyncClient) -> None:
        created = await create_child(auth_client)
        await auth_client.post(f"/api/children/{created['id']}/feedings", json=FORMULA)
        assert (await auth_client.delete(f"/api/children/{created['id']}")).status_code == 204
        assert (await auth_client.get(f"/api/children/{created['id']}")).status_code == 404
        assert (await auth_client.get("/api/children")).json() == []

    @pytest.mark.parametrize(
        "overrides",
        [
            {"birth_date": born(61)},
            {"birth_date": (today() + dt.timedelta(days=2)).isoformat()},
            {"birth_date": "2026-13-01"},
            {"age_months": 8},  # a typed age is refused, never converted
            {"weight_kg": 0},
            {"allergies": ["gluten"]},
            {"diet_preference": "keto"},
            {"birth_date": born(40)},  # height required from 36 months
            {"nickname": "bean"},
            {"activity_level": "olympic"},
            {"doctors_note": "no honey"},  # the old single field is gone
            {"notes": [{"kind": "doctor", "text": "   "}]},
            {"notes": [{"kind": "doctor", "text": "x"}, {"kind": "doctor", "text": "x"}]},
            {"notes": [{"kind": "doctor", "text": f"row {i}"} for i in range(21)]},
            {"notes": [{"kind": "nurse", "text": "no honey"}]},
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
        theirs = await create_child(api_client, birth_date=born(20), sex="male")

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
        measured = await measure(api_client, mine["id"])

        sign_in(api_client, other_user)
        for method, path, body in [
            ("GET", f"/api/children/{mine['id']}", None),
            ("PUT", f"/api/children/{mine['id']}", CHILD),
            ("DELETE", f"/api/children/{mine['id']}", None),
            ("GET", f"/api/children/{mine['id']}/feedings", None),
            ("POST", f"/api/children/{mine['id']}/feedings", FORMULA),
            ("DELETE", f"/api/children/{mine['id']}/feedings/{fed['entry']['id']}", None),
            ("GET", f"/api/children/{mine['id']}/growth", None),
            ("GET", f"/api/children/{mine['id']}/growth/curves", None),
            ("POST", f"/api/children/{mine['id']}/growth", MEASUREMENT),
            ("DELETE", f"/api/children/{mine['id']}/growth/{measured['id']}", None),
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
        assert len(await growth_list(api_client, mine["id"])) == 1

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
            f"/api/children/{mine['id']}/growth",
            f"/api/children/{mine['id']}/growth/curves",
        ):
            response = await api_client.get(path)
            assert response.status_code == 401
            assert response.json() == {"detail": "Sign in to continue"}


class TestDailyTargets:
    """GET /api/children/{id}/targets (day-9 child-profile spec): a derived, owner-only read."""

    async def test_owner_reads_the_ordered_set_with_disclaimer(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(auth_client)  # 8 months, 8.5 kg, omnivore
        response = await auth_client.get(f"/api/children/{child['id']}/targets")
        assert response.status_code == 200
        body = response.json()
        # Display order: iron is promoted ahead of protein for infants.
        assert [row["nutrient"] for row in body["targets"]["items"]] == [
            "calories",
            "iron",
            "protein",
            "vitamin_d",
            "zinc",
            "calcium",
        ]
        assert body["diet_preference"] == "omnivore"
        assert body["doctor_notes_present"] is False and body["preferences_present"] is False
        assert "not" in body["disclaimer"] and "pediatrician" in body["disclaimer"]

    async def test_deterministic_and_unflagged_with_no_logged_days(
        self, auth_client: AsyncClient
    ) -> None:
        """No language-model call and no log read: byte-identical, and never a flag."""
        child = await create_child(
            auth_client,
            notes=[
                {"kind": "doctor", "text": "Limit to 650 kcal per day."},
                {"kind": "preference", "text": "no pork"},
            ],
        )
        first = await auth_client.get(f"/api/children/{child['id']}/targets")
        second = await auth_client.get(f"/api/children/{child['id']}/targets")
        assert first.status_code == second.status_code == 200
        assert first.content == second.content
        body = first.json()
        assert body["doctor_notes_present"] is True and body["preferences_present"] is True
        # The note is disclosed, not applied (Decision 6): calories stay the general 678.
        assert body["targets"]["calories"]["calories"] == 678
        for row in body["targets"]["items"]:
            assert row["flag"] is None and row["intake_average"] is None, row["nutrient"]

    async def test_logged_days_put_flags_on_tracked_rows_only(
        self, auth_client: AsyncClient
    ) -> None:
        """chat-ui spec: a tracked target shows progress and flag once complete days exist."""
        child = await create_child(auth_client)
        for days_ago in (1, 2, 3):
            fed_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)
            await log_feed(auth_client, child["id"], fed_at=fed_at.isoformat())
        body = (await auth_client.get(f"/api/children/{child['id']}/targets")).json()
        rows = {row["nutrient"]: row for row in body["targets"]["items"]}
        for key in ("calories", "protein", "iron", "calcium"):
            assert rows[key]["flag"] in {"below", "adequate", "above"}, key
            assert rows[key]["intake_average"] is not None, key
        # 150 ml of formula a day is far below the 678 kcal target.
        assert rows["calories"]["flag"] == "below"
        for key in ("vitamin_d", "zinc"):
            assert rows[key]["flag"] is None and rows[key]["intake_average"] is None, key

    async def test_vegan_profile_gains_b12_and_the_dha_advisory(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(
            auth_client, birth_date=born(30), weight_kg=13, diet_preference="vegan"
        )
        body = (await auth_client.get(f"/api/children/{child['id']}/targets")).json()
        rows = {row["nutrient"]: row for row in body["targets"]["items"]}
        assert rows["vitamin_b12"]["amount"] == 0.9 and rows["vitamin_b12"]["unit"] == "µg"
        assert rows["dha"]["amount"] is None and rows["dha"]["advisory"]

    async def test_changing_diet_changes_the_set_but_never_a_number(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(auth_client, birth_date=born(30), weight_kg=13)
        before = (await auth_client.get(f"/api/children/{child['id']}/targets")).json()
        replaced = await auth_client.put(
            f"/api/children/{child['id']}",
            json={**CHILD, "birth_date": born(30), "weight_kg": 13, "diet_preference": "vegan"},
        )
        assert replaced.status_code == 200
        after = (await auth_client.get(f"/api/children/{child['id']}/targets")).json()
        before_rows = {row["nutrient"]: row for row in before["targets"]["items"]}
        after_rows = {row["nutrient"]: row for row in after["targets"]["items"]}
        assert "vitamin_b12" not in before_rows and "vitamin_b12" in after_rows
        assert "dha" not in before_rows and "dha" in after_rows
        for key in before_rows.keys() & after_rows.keys():
            assert before_rows[key]["amount"] == after_rows[key]["amount"], key

    async def test_non_owner_gets_the_same_refusal_as_a_direct_read(
        self, api_client: AsyncClient, user: User, other_user: User
    ) -> None:
        sign_in(api_client, user)
        mine = await create_child(api_client)

        sign_in(api_client, other_user)
        as_non_owner = await api_client.get(f"/api/children/{mine['id']}/targets")
        direct_read = await api_client.get(f"/api/children/{mine['id']}")
        as_nonexistent = await api_client.get(f"/api/children/{NOWHERE}/targets")
        assert as_non_owner.status_code == 404
        assert as_non_owner.status_code == direct_read.status_code == as_nonexistent.status_code
        assert as_non_owner.content == as_nonexistent.content
        # No target value, age, or diet preference is disclosed (hard rule 9).
        for fragment in ("678", "amount", "diet", "age"):
            assert fragment not in as_non_owner.text

    async def test_unauthenticated_is_refused(self, api_client: AsyncClient, user: User) -> None:
        sign_in(api_client, user)
        mine = await create_child(api_client)
        api_client.cookies.clear()
        response = await api_client.get(f"/api/children/{mine['id']}/targets")
        assert response.status_code == 401
        assert response.json() == {"detail": "Sign in to continue"}

    async def test_a_child_who_aged_out_is_refused_with_the_range_named(
        self, auth_client: AsyncClient, db_session: AsyncSession, user: User
    ) -> None:
        """child-profile spec: a stored profile past 60 months (which the write API would no
        longer accept) answers 422 wherever the chat context is built, not 500."""
        aged_out = ChildProfile(
            user_id=user.id,
            birth_date=birth_date_for(61, today()),
            weight_kg=Decimal("18.0"),
            height_cm=Decimal("106.0"),
            sex=Sex.MALE,
        )
        db_session.add(aged_out)
        await db_session.commit()
        profile = await profile_of(auth_client, str(aged_out.id))
        assert profile["age_months"] == 61  # the read itself still works
        targets = await auth_client.get(f"/api/children/{aged_out.id}/targets")
        assert targets.status_code == 422 and targets.json()["detail"] == AGE_OUT_OF_RANGE_DETAIL
        chat = await auth_client.post("/api/chat", json={"message": "hi", "stream": False})
        assert chat.status_code == 422 and chat.json()["detail"] == AGE_OUT_OF_RANGE_DETAIL


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


class TestGrowthLog:
    """``/api/children/{id}/growth`` (growth-tracking spec): raw rows stored, the age on the
    day and the WHO assessment derived on every read, the newest measurement carried onto
    the profile."""

    async def test_newest_first_with_the_age_on_the_measurement_day(
        self, auth_client: AsyncClient
    ) -> None:
        # Fixed dates for the arithmetic: born 10 January, measured the day before and the
        # day of the four-month anniversary (child-profile spec scenario).
        child = await create_child(auth_client, birth_date="2026-01-10")
        for day, weight in (("2026-05-09", 6.9), ("2026-05-10", 7.0)):
            await measure(auth_client, child["id"], measured_on=day, weight_kg=weight)
        listed = await growth_list(auth_client, child["id"])
        assert [(m["measured_on"], m["age_months"]) for m in listed] == [
            ("2026-05-10", 4),
            ("2026-05-09", 3),
        ]
        for row in listed:
            assert row["assessment"]["age_months"] == row["age_months"]
            assert row["assessment"]["source"] == "WHO Child Growth Standards (2006)"
            uuid.UUID(row["id"])

    async def test_exact_age_spreads_measurements_within_a_month(
        self, auth_client: AsyncClient
    ) -> None:
        """growth-charts: two weigh-ins in one completed month sit apart on an age axis."""
        child = await create_child(auth_client, birth_date="2026-01-10")
        first = await measure(auth_client, child["id"], measured_on="2026-05-12", weight_kg=6.9)
        second = await measure(auth_client, child["id"], measured_on="2026-05-25", weight_kg=7.0)
        assert first["age_months"] == second["age_months"] == 4
        assert second["age_months_exact"] - first["age_months_exact"] == pytest.approx(0.43, 0.02)
        assert first["age_months_exact"] == pytest.approx(122 / 30.4375, abs=0.01)

    async def test_percentile_curves_for_the_child_sex_and_table(
        self, auth_client: AsyncClient
    ) -> None:
        """growth-tracking spec: nine curves per indicator, the 50th equal to the median."""
        child = await create_child(auth_client)  # girl, 8 months
        response = await auth_client.get(f"/api/children/{child['id']}/growth/curves")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sex"] == "female" and body["age_months"] == 8
        assert body["source"] == "WHO Child Growth Standards (2006)"
        sets = {s["indicator"]: s for s in body["indicators"]}
        assert set(sets) == {
            "weight_for_age",
            "length_height_for_age",
            "weight_for_length_height",
            "bmi_for_age",
        }
        for curve_set in sets.values():
            assert [c["percentile"] for c in curve_set["curves"]] == list(range(10, 100, 10))
            assert all(len(c["values"]) == len(curve_set["xs"]) for c in curve_set["curves"])
        _, median, _ = get_growth_table().monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        p50 = next(c for c in sets["weight_for_age"]["curves"] if c["percentile"] == 50)
        assert p50["values"][8] == round(median, 1)
        assert sets["weight_for_length_height"]["x_label_table"] == "length"
        assert (
            sets["weight_for_length_height"]["xs"][0],
            sets["weight_for_length_height"]["xs"][-1],
        ) == (45.0, 110.0)

        older = await create_child(auth_client, birth_date=born(30), weight_kg=13, sex="male")
        body = (await auth_client.get(f"/api/children/{older['id']}/growth/curves")).json()
        wflh = next(s for s in body["indicators"] if s["indicator"] == "weight_for_length_height")
        assert wflh["x_label_table"] == "height" and (wflh["xs"][0], wflh["xs"][-1]) == (
            65.0,
            120.0,
        )

    async def test_height_unlocks_four_indicators(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        with_height = await measure(auth_client, child["id"])
        yesterday = (today() - dt.timedelta(days=1)).isoformat()
        without = await measure(
            auth_client, child["id"], measured_on=yesterday, weight_kg=8.6, height_cm=None
        )
        assert len(with_height["assessment"]["indicators"]) == 4
        assert with_height["assessment"]["skipped"] == []
        assert [i["indicator"] for i in without["assessment"]["indicators"]] == ["weight_for_age"]
        assert len(without["assessment"]["skipped"]) == 3
        assert "length or height" in without["assessment"]["skipped"][0]["reason"]
        assert without["height_cm"] is None

    async def test_median_weight_reads_as_the_50th_percentile(
        self, auth_client: AsyncClient
    ) -> None:
        """Recomputed on read from the WHO table, not stored: the median for the child's
        sex and age on the measurement day sits at the 50th percentile."""
        child = await create_child(auth_client)  # girl, 8 months today
        _, median, _ = get_growth_table().monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        row = await measure(auth_client, child["id"], weight_kg=round(median, 2), height_cm=None)
        [weight_for_age] = row["assessment"]["indicators"]
        # The stored value is fixed-point to two decimals, so allow that rounding.
        assert abs(weight_for_age["percentile"] - 50.0) <= 0.5
        assert weight_for_age["band"] == "expected"

    async def test_the_newest_measurement_sets_the_profile(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)  # 8.5 kg, no height
        await measure(auth_client, child["id"])  # today: 8.7 kg, 70 cm
        profile = await profile_of(auth_client, child["id"])
        assert (profile["weight_kg"], profile["height_cm"]) == (8.7, 70.0)

        a_month_ago = (today() - dt.timedelta(days=30)).isoformat()
        await measure(auth_client, child["id"], measured_on=a_month_ago, weight_kg=8.2)
        profile = await profile_of(auth_client, child["id"])
        assert (profile["weight_kg"], profile["height_cm"]) == (8.7, 70.0)  # back-dated: no change

    async def test_newest_without_height_keeps_the_profile_height(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(auth_client)
        yesterday = (today() - dt.timedelta(days=1)).isoformat()
        await measure(auth_client, child["id"], measured_on=yesterday, weight_kg=8.6, height_cm=70)
        await measure(auth_client, child["id"], weight_kg=8.8, height_cm=None)
        profile = await profile_of(auth_client, child["id"])
        assert (profile["weight_kg"], profile["height_cm"]) == (8.8, 70.0)

    async def test_editing_the_profile_logs_nothing(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        replaced = await auth_client.put(
            f"/api/children/{child['id']}", json={**CHILD, "weight_kg": 9.1}
        )
        assert replaced.status_code == 200
        assert await growth_list(auth_client, child["id"]) == []

    async def test_rejections(self, auth_client: AsyncClient) -> None:
        child = await create_child(auth_client)
        birth = dt.date.fromisoformat(CHILD["birth_date"])
        before_birth = (birth - dt.timedelta(days=1)).isoformat()
        response = await auth_client.post(
            f"/api/children/{child['id']}/growth",
            json={**MEASUREMENT, "measured_on": before_birth},
        )
        assert response.status_code == 422 and "date of birth" in response.json()["detail"]

        ahead = (today() + dt.timedelta(days=2)).isoformat()
        response = await auth_client.post(
            f"/api/children/{child['id']}/growth", json={**MEASUREMENT, "measured_on": ahead}
        )
        assert response.status_code == 422

        for body in (
            {**MEASUREMENT, "weight_kg": 0},
            {**MEASUREMENT, "height_cm": 0},
            {**MEASUREMENT, "id": str(NOWHERE)},  # ids are server-generated
        ):
            response = await auth_client.post(f"/api/children/{child['id']}/growth", json=body)
            assert response.status_code == 422, body
        assert await growth_list(auth_client, child["id"]) == []

    async def test_same_day_twice_is_409_and_the_first_stands(
        self, auth_client: AsyncClient
    ) -> None:
        child = await create_child(auth_client)
        first = await measure(auth_client, child["id"])
        again = await auth_client.post(
            f"/api/children/{child['id']}/growth", json={**MEASUREMENT, "weight_kg": 9.9}
        )
        assert again.status_code == 409 and "that day" in again.json()["detail"]
        listed = await growth_list(auth_client, child["id"])
        assert [m["id"] for m in listed] == [first["id"]] and listed[0]["weight_kg"] == 8.7
        assert (await profile_of(auth_client, child["id"]))["weight_kg"] == 8.7

    async def test_sixty_months_is_still_assessed(self, auth_client: AsyncClient) -> None:
        child = await create_child(
            auth_client, birth_date=born(60), weight_kg=18, height_cm=106, sex="male"
        )
        row = await measure(auth_client, child["id"], weight_kg=18.2, height_cm=106.5)
        assert row["age_months"] == 60 and len(row["assessment"]["indicators"]) == 4

    async def test_delete_removes_one_and_leaves_the_profile(
        self, auth_client: AsyncClient, api_client: AsyncClient, other_user: User, user: User
    ) -> None:
        child = await create_child(auth_client)
        yesterday = (today() - dt.timedelta(days=1)).isoformat()
        older = await measure(auth_client, child["id"], measured_on=yesterday, weight_kg=8.6)
        newest = await measure(auth_client, child["id"])
        response = await auth_client.delete(f"/api/children/{child['id']}/growth/{newest['id']}")
        assert response.status_code == 204
        assert [m["id"] for m in await growth_list(auth_client, child["id"])] == [older["id"]]
        assert (await profile_of(auth_client, child["id"]))["weight_kg"] == 8.7  # not rolled back

        # Another child's measurement id is refused exactly like a nonexistent one.
        sign_in(api_client, other_user)
        theirs = await create_child(api_client, sex="male")
        sign_in(api_client, user)
        foreign = await api_client.delete(f"/api/children/{child['id']}/growth/{theirs['id']}")
        nowhere = await api_client.delete(f"/api/children/{child['id']}/growth/{NOWHERE}")
        assert foreign.status_code == nowhere.status_code == 404
        assert foreign.content == nowhere.content


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
        await create_child(auth_client, birth_date=born(30), sex="male")
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
