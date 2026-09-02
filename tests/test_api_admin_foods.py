"""``/api/admin/foods`` against PostgreSQL (food-table-admin spec)."""

import json
import logging
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_auth_settings
from backend.core.config import Settings
from backend.models import FoodTableRevision, User
from backend.nutrition.foods import FoodNotFoundError, get_food_table, reset_food_table_cache
from backend.schemas.tools import MealPlanRequest
from backend.tools.meal_plan import generate_meal_plan
from tests.conftest import TEST_SESSION_SECRET, sign_in
from tests.test_api_children import create_child

pytestmark = pytest.mark.db

PEAR = {
    "id": "pear_ripe_test",
    "name": "Pear, ripe and soft (test)",
    "category": "fruit",
    "serving_size": 60,
    "serving_unit": "g",
    "calories": 34,
    "protein_g": 0.2,
    "fat_g": 0.1,
    "carbohydrate_g": 9.0,
    "iron_mg": 0.1,
    "calcium_mg": 5,
    "allergens": [],
    "choking_hazard": False,
    "contains_honey": False,
    "commonly_unpasteurized": False,
    "min_age_months": 6,
    "source": "USDA FDC 169118",
}
CSV_HEADER = (
    "id,name,category,serving_size,serving_unit,calories,protein_g,fat_g,carbohydrate_g,"
    "iron_mg,calcium_mg,zinc_mg,vitamin_a_ug,iodine_ug,vitamin_b12_ug,folate_ug,"
    "vitamin_c_mg,fiber_g,allergens,choking_hazard,contains_honey,commonly_unpasteurized,"
    "min_age_months,source\n"
)
ADMIN = "/api/admin/foods"


@pytest.fixture(autouse=True)
def served_table_is_reset():
    """A write swaps the process-wide table; the database rolls back, so must the cache."""
    reset_food_table_cache()
    yield
    reset_food_table_cache()


@pytest_asyncio.fixture
async def admin_client(api_client: AsyncClient, user: User) -> AsyncClient:
    app = api_client._transport.app  # type: ignore[attr-defined]
    settings = Settings(
        database_url="postgresql://unused:unused@unused/unused",
        session_secret=TEST_SESSION_SECRET,
        admin_emails=user.email,
        _env_file=None,
    )
    app.dependency_overrides[get_auth_settings] = lambda: settings
    sign_in(api_client, user)
    return api_client


async def latest_revision(db: AsyncSession) -> FoodTableRevision:
    result = await db.execute(
        select(FoodTableRevision).order_by(FoodTableRevision.revision.desc()).limit(1)
    )
    return result.scalar_one()


class TestReadAndRole:
    async def test_admin_lists_the_seeded_table(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(ADMIN)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["revision"] == 1 and body["version"] == "db-1"
        assert len(body["foods"]) == 57 and all(f["is_active"] for f in body["foods"])

    async def test_non_admin_is_refused(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get(ADMIN)
        assert response.status_code == 403 and response.json() == {
            "detail": "Admin access required"
        }


class TestWrites:
    async def test_create_bumps_the_revision_and_reaches_the_picker(
        self, admin_client: AsyncClient, db_session: AsyncSession, user: User
    ) -> None:
        response = await admin_client.post(ADMIN, json=PEAR)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["revision"] == 2 and body["version"] == "db-2"
        assert body["food"]["id"] == PEAR["id"] and body["food"]["is_active"] is True
        picker = await admin_client.get("/api/foods")
        assert PEAR["id"] in {f["id"] for f in picker.json()}
        assert get_food_table().version == "db-2"
        row = await latest_revision(db_session)
        assert row.revision == 2 and row.actor_user_id == user.id
        assert row.summary == f"Created {PEAR['id']}"
        assert len(row.table["foods"]) == 58

    async def test_duplicate_id_is_409_and_bad_entries_are_422(
        self, admin_client: AsyncClient
    ) -> None:
        assert (await admin_client.post(ADMIN, json={**PEAR, "id": "avocado"})).status_code == 409
        for body in (
            {**PEAR, "min_age_months": 4},
            {k: v for k, v in PEAR.items() if k != "choking_hazard"},
            {k: v for k, v in PEAR.items() if k != "source"},
            {**PEAR, "category": "milk_feed", "min_age_months": 0},
            {**PEAR, "allergens": ["gluten"]},
        ):
            response = await admin_client.post(ADMIN, json=body)
            assert response.status_code == 422, body
        assert (await admin_client.get(ADMIN)).json()["revision"] == 1

    async def test_edit_replaces_the_entry(self, admin_client: AsyncClient) -> None:
        avocado = next(
            f for f in (await admin_client.get(ADMIN)).json()["foods"] if f["id"] == "avocado"
        )
        edited = {**avocado, "calories": avocado["calories"] + 1, "source": "USDA FDC 171705"}
        response = await admin_client.put(f"{ADMIN}/avocado", json=edited)
        assert response.status_code == 200, response.text
        assert response.json()["food"]["calories"] == avocado["calories"] + 1
        assert response.json()["revision"] == 2
        mismatch = await admin_client.put(f"{ADMIN}/avocado", json={**edited, "id": "pear"})
        assert mismatch.status_code == 422
        missing = await admin_client.put(f"{ADMIN}/nope", json={**edited, "id": "nope"})
        assert missing.status_code == 404

    async def test_protected_milk_feed_cannot_change_category_or_deactivate(
        self, admin_client: AsyncClient
    ) -> None:
        formula = next(
            f
            for f in (await admin_client.get(ADMIN)).json()["foods"]
            if f["id"] == "infant_formula_iron_fortified"
        )
        moved = {**formula, "category": "dairy", "min_age_months": 12, "source": "s"}
        assert (await admin_client.put(f"{ADMIN}/{formula['id']}", json=moved)).status_code == 409
        assert (await admin_client.post(f"{ADMIN}/{formula['id']}/deactivate")).status_code == 409


class TestDeactivation:
    async def test_inactive_food_leaves_picker_plans_and_lookup_but_still_prices(
        self, admin_client: AsyncClient
    ) -> None:
        child = await create_child(admin_client)
        fed = await admin_client.post(
            f"/api/children/{child['id']}/feedings",
            json={
                "fed_at": "2026-08-27T09:00:00Z",
                "feeding_type": "solid",
                "food_id": "banana_mashed",
                "quantity": 60,
                "unit": "g",
            },
        )
        assert fed.status_code == 201

        response = await admin_client.post(f"{ADMIN}/banana_mashed/deactivate")
        assert response.status_code == 200 and response.json()["food"]["is_active"] is False
        assert response.json()["revision"] == 2
        assert "banana_mashed" not in {
            f["id"] for f in (await admin_client.get("/api/foods")).json()
        }
        with pytest.raises(FoodNotFoundError):
            get_food_table().resolve("bananas")
        [entry] = (await admin_client.get(f"/api/children/{child['id']}/feedings")).json()
        assert entry["nutrients"]["calories"] > 0  # the stored feed still prices

        again = await admin_client.post(f"{ADMIN}/banana_mashed/deactivate")
        assert again.status_code == 200 and again.json()["revision"] == 2  # idempotent, no write
        back = await admin_client.post(f"{ADMIN}/banana_mashed/activate")
        assert back.status_code == 200 and back.json()["revision"] == 3
        assert "banana_mashed" in {f["id"] for f in (await admin_client.get("/api/foods")).json()}
        assert (await admin_client.post(f"{ADMIN}/nope/deactivate")).status_code == 404

    async def test_a_deactivated_food_is_never_planned_and_the_plan_names_the_revision(
        self, admin_client: AsyncClient, caplog
    ) -> None:
        caplog.set_level(logging.INFO, logger="backend.tools.audit")
        await admin_client.post(f"{ADMIN}/infant_cereal_iron_fortified/deactivate")
        result = await generate_meal_plan(
            MealPlanRequest(age_months=9, weight_kg=8.8, sex="female"), None
        )
        assert "infant_cereal_iron_fortified" not in {i.food_id for i in result.items}
        assert result.food_table_version == "db-2"
        [record] = [
            json.loads(r.getMessage().removeprefix("meal_plan_audit "))
            for r in caplog.records
            if r.name == "backend.tools.audit" and r.getMessage().startswith("meal_plan_audit ")
        ]
        assert record["food_table_version"] == "db-2"


class TestMicronutrients:
    async def test_filled_and_blank_round_trip(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        payload = {**PEAR, "zinc_mg": 0.06, "vitamin_c_mg": 2.7, "fiber_g": 1.9}
        response = await admin_client.post(ADMIN, json=payload)
        assert response.status_code == 201, response.text
        food = response.json()["food"]
        assert food["zinc_mg"] == 0.06 and food["vitamin_c_mg"] == 2.7 and food["fiber_g"] == 1.9
        # Blank fields read back as "not measured", never zero.
        assert food["vitamin_a_ug"] is None and food["iodine_ug"] is None
        listed = await admin_client.get(ADMIN)
        [stored] = [f for f in listed.json()["foods"] if f["id"] == PEAR["id"]]
        assert stored["zinc_mg"] == 0.06 and stored["folate_ug"] is None

    async def test_negative_micronutrient_is_refused_and_writes_nothing(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        response = await admin_client.post(ADMIN, json={**PEAR, "iodine_ug": -1})
        assert response.status_code == 422, response.text
        assert "iodine_ug" in response.text
        row = await latest_revision(db_session)
        assert row.revision == 1


class TestImport:
    def csv(self, *rows: str) -> str:
        return CSV_HEADER + "".join(rows)

    async def test_one_bad_row_writes_nothing_and_is_named(self, admin_client: AsyncClient) -> None:
        content = self.csv(
            "pear_a,Pear A,fruit,60,g,34,0.2,0.1,9,0.1,5,0.06,,,,,2.7,1.9,"
            ",false,false,false,6,USDA\n",
            "pear_b,Pear B,fruit,60,g,34,0.2,0.1,9,-1,5,,,,,,,,,false,false,false,6,USDA\n",
        )
        response = await admin_client.post(
            f"{ADMIN}/import", json={"format": "csv", "content": content, "dry_run": True}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["applied"] is False and body["created"] == [] and body["revision"] == 1
        [error] = body["errors"]
        assert (error["row"], error["id"], error["field"]) == (2, "pear_b", "iron_mg")

    async def test_clean_import_writes_one_revision(self, admin_client: AsyncClient) -> None:
        yaml_text = (
            "source: USDA FoodData Central\n"
            "foods:\n"
            f"  - {json.dumps({k: v for k, v in PEAR.items() if k != 'source'})}\n"
            f"  - {json.dumps({**PEAR, 'id': 'plum_ripe_test', 'name': 'Plum, ripe (test)'})}\n"
        )
        dry = await admin_client.post(
            f"{ADMIN}/import", json={"format": "yaml", "content": yaml_text, "dry_run": True}
        )
        assert dry.json()["applied"] is False and dry.json()["created"] == [
            "pear_ripe_test",
            "plum_ripe_test",
        ]
        assert dry.json()["revision"] == 1
        real = await admin_client.post(
            f"{ADMIN}/import", json={"format": "yaml", "content": yaml_text}
        )
        body = real.json()
        assert body["applied"] is True and body["revision"] == 2 and body["version"] == "db-2"
        assert len((await admin_client.get("/api/foods")).json()) == 59
        again = await admin_client.post(
            f"{ADMIN}/import",
            json={"format": "yaml", "content": yaml_text, "mode": "create_only"},
        )
        assert again.json()["applied"] is False
        assert {e["message"] for e in again.json()["errors"]} == {"already exists"}
        same = await admin_client.post(
            f"{ADMIN}/import", json={"format": "yaml", "content": yaml_text}
        )
        assert same.json()["applied"] is False and same.json()["unchanged"] == [
            "pear_ripe_test",
            "plum_ripe_test",
        ]
        assert same.json()["revision"] == 2

    async def test_unreadable_or_oversized_files_are_422(self, admin_client: AsyncClient) -> None:
        bad = await admin_client.post(
            f"{ADMIN}/import", json={"format": "yaml", "content": "foods: [x"}
        )
        assert bad.status_code == 422
        big = await admin_client.post(
            f"{ADMIN}/import", json={"format": "yaml", "content": "x" * (1_048_576 + 1)}
        )
        assert big.status_code == 422


class TestOwnershipUnchanged:
    async def test_admin_routes_do_not_expose_children(
        self, admin_client: AsyncClient, other_user: User
    ) -> None:
        """The role is about the food table only; another account's child is still 404."""
        theirs_id = uuid.uuid7()
        assert (await admin_client.get(f"/api/children/{theirs_id}")).status_code == 404
