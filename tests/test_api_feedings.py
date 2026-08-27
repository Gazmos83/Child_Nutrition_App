"""POST /api/feedings and GET /api/foods are stateless (change 2 task 4.1; feeding-log spec)."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.nutrition.foods import get_food_table


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


class TestFeedings:
    def test_valid_formula_returns_id_and_nutrients(self, client) -> None:
        response = client.post(
            "/api/feedings",
            json={"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula", "quantity": 150},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["entry"]["id"] and len(body["entry"]["id"]) == 36
        assert body["food_id"] == "infant_formula_iron_fortified"
        assert body["quantified"] is True
        assert body["nutrients"]["calories"] == 100.5
        assert body["nutrients"]["protein_g"] == 2.1
        assert body["source"]

    def test_unknown_solid_names_the_id(self, client) -> None:
        response = client.post(
            "/api/feedings",
            json={
                "fed_at": "2026-08-27T09:00:00Z",
                "feeding_type": "solid",
                "food_id": "dragonfruit",
                "quantity": 30,
                "unit": "g",
            },
        )
        assert response.status_code == 422
        assert "dragonfruit" in response.json()["detail"]

    def test_wrong_unit_for_a_solid_is_422(self, client) -> None:
        response = client.post(
            "/api/feedings",
            json={
                "fed_at": "2026-08-27T09:00:00Z",
                "feeding_type": "solid",
                "food_id": "avocado",
                "quantity": 30,
                "unit": "ml",
            },
        )
        assert response.status_code == 422
        assert "measured in g" in response.json()["detail"]

    def test_shape_errors_are_422_before_the_table(self, client) -> None:
        for body in (
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "formula"},  # no quantity
            {"fed_at": "2026-08-27T09:00:00", "feeding_type": "breastmilk"},  # naive time
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "snack", "quantity": 1},
            {"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "water", "quantity": 50, "x": 1},
        ):
            assert client.post("/api/feedings", json=body).status_code == 422, body

    def test_breastmilk_without_quantity_is_accepted(self, client) -> None:
        response = client.post(
            "/api/feedings", json={"fed_at": "2026-08-27T09:00:00Z", "feeding_type": "breastmilk"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["quantified"] is False and body["nutrients"]["calories"] == 0
        assert body["food_id"] == "breast_milk"


class TestFoods:
    def test_every_table_entry_listed_once(self, client) -> None:
        response = client.get("/api/foods")
        assert response.status_code == 200
        foods = response.json()
        table = get_food_table()
        assert [f["id"] for f in foods] == [f.id for f in table.foods]
        assert len({f["id"] for f in foods}) == len(table)
        for food in foods:
            assert set(food) == {
                "id",
                "name",
                "category",
                "serving_size",
                "serving_unit",
                "min_age_months",
            }
            assert food["serving_unit"] in {"ml", "g"} and food["min_age_months"] >= 0
        formula = next(f for f in foods if f["id"] == "infant_formula_iron_fortified")
        assert formula["category"] == "milk_feed" and formula["serving_unit"] == "ml"
