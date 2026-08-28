"""GET /api/foods is public and stateless (feeding-log spec).

The feeding log itself moved under ``/api/children/{child_id}/feedings`` on Day 6 and is
covered against PostgreSQL in ``tests/test_api_children.py``.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.nutrition.foods import get_food_table


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


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
