"""Administrative edits as pure functions over the table (food-table-admin design Decisions
1, 4, 6)."""

import pytest

from backend.nutrition.food_admin import (
    PROTECTED_FOOD_IDS,
    AdminRuleError,
    DuplicateFoodError,
    FoodWrite,
    apply_write,
    parse_import,
    plan_import,
    set_active,
    snapshot,
    validate_table,
)
from backend.nutrition.foods import FoodNotFoundError, FoodTable, load_food_table
from tests.test_nutrition_foods import LENTILS_ENTRY, VALID_ENTRY, write_table

MILK = {
    **VALID_ENTRY,
    "id": "breast_milk",
    "name": "Breast milk",
    "category": "milk_feed",
    "min_age_months": 0,
    "serving_size": 100,
    "serving_unit": "ml",
}
PEAR = {**VALID_ENTRY, "id": "pear", "name": "Pear, ripe", "source": "USDA FDC 169118"}


@pytest.fixture
def table(tmp_path) -> FoodTable:
    return load_food_table(write_table(tmp_path, VALID_ENTRY, LENTILS_ENTRY, MILK)).table


class TestWrites:
    def test_create_appends_and_validates_whole(self, table: FoodTable) -> None:
        updated = apply_write(table, FoodWrite.model_validate(PEAR), create=True)
        assert [f.id for f in updated.foods] == ["banana", "lentils", "breast_milk", "pear"]
        assert updated.by_id()["pear"].source == "USDA FDC 169118"
        assert snapshot(updated)["foods"][-1]["id"] == "pear"

    def test_source_is_required_on_a_write(self) -> None:
        with pytest.raises(Exception, match="source"):
            FoodWrite.model_validate({**PEAR, "source": None})

    def test_duplicate_create_is_a_conflict(self, table: FoodTable) -> None:
        with pytest.raises(DuplicateFoodError) as excinfo:
            apply_write(
                table, FoodWrite.model_validate({**VALID_ENTRY, "source": "s"}), create=True
            )
        assert excinfo.value.conflict

    def test_replace_keeps_position_and_needs_an_existing_id(self, table: FoodTable) -> None:
        changed = FoodWrite.model_validate({**VALID_ENTRY, "calories": 50, "source": "s"})
        updated = apply_write(table, changed, create=False)
        assert [f.id for f in updated.foods] == ["banana", "lentils", "breast_milk"]
        assert updated.by_id()["banana"].calories == 50
        with pytest.raises(FoodNotFoundError):
            apply_write(table, FoodWrite.model_validate(PEAR), create=False)

    def test_milk_feed_category_is_reserved_and_protected(self, table: FoodTable) -> None:
        with pytest.raises(AdminRuleError, match="reserved"):
            apply_write(
                table,
                FoodWrite.model_validate({**PEAR, "category": "milk_feed", "min_age_months": 0}),
                create=True,
            )
        with pytest.raises(AdminRuleError, match="must stay a milk feed") as excinfo:
            apply_write(
                table,
                FoodWrite.model_validate(
                    {**MILK, "category": "dairy", "min_age_months": 6, "source": "s"}
                ),
                create=False,
            )
        assert excinfo.value.conflict

    def test_a_solid_under_six_months_is_refused_naming_the_entry(self, table: FoodTable) -> None:
        with pytest.raises(Exception, match="at least 6"):
            FoodWrite.model_validate({**PEAR, "min_age_months": 4})


class TestActivation:
    def test_deactivate_and_reactivate(self, table: FoodTable) -> None:
        updated, changed = set_active(table, "banana", False)
        assert changed and updated.by_id()["banana"].is_active is False
        again, changed_again = set_active(updated, "banana", False)
        assert not changed_again and again == updated
        back, _ = set_active(updated, "banana", True)
        assert back.by_id()["banana"].is_active is True

    def test_protected_milk_feeds_stay_active(self, table: FoodTable) -> None:
        for food_id in PROTECTED_FOOD_IDS & set(table.by_id()):
            with pytest.raises(AdminRuleError) as excinfo:
                set_active(table, food_id, False)
            assert excinfo.value.conflict
        with pytest.raises(FoodNotFoundError):
            set_active(table, "nope", False)


class TestValidateTable:
    def test_names_the_offending_entry(self) -> None:
        with pytest.raises(ValueError, match=r"foods\[1\] \(lentils\)\.calories"):
            validate_table(
                {"source": "s", "foods": [VALID_ENTRY, {**LENTILS_ENTRY, "calories": -1}]}
            )
        with pytest.raises(ValueError, match="listed twice"):
            validate_table({"source": "s", "foods": [VALID_ENTRY, VALID_ENTRY]})


CSV_HEADER = (
    "id,name,category,serving_size,serving_unit,calories,protein_g,fat_g,carbohydrate_g,"
    "iron_mg,calcium_mg,zinc_mg,vitamin_a_ug,iodine_ug,vitamin_b12_ug,folate_ug,"
    "vitamin_c_mg,fiber_g,allergens,choking_hazard,contains_honey,commonly_unpasteurized,"
    "min_age_months,source\n"
)

# The pre-micronutrient column set: files written against it must keep importing.
LEGACY_CSV_HEADER = (
    "id,name,category,serving_size,serving_unit,calories,protein_g,fat_g,carbohydrate_g,"
    "iron_mg,calcium_mg,allergens,choking_hazard,contains_honey,commonly_unpasteurized,"
    "min_age_months,source\n"
)


class TestParseImport:
    def test_yaml_list_and_mapping(self) -> None:
        rows, source = parse_import("yaml", "- id: pear\n  name: Pear\n")
        assert rows == [{"id": "pear", "name": "Pear"}] and source is None
        rows, source = parse_import("yaml", "source: USDA\nfoods:\n  - id: pear\n")
        assert rows == [{"id": "pear"}] and source == "USDA"
        with pytest.raises(ValueError, match="list of foods"):
            parse_import("yaml", "just a string")
        with pytest.raises(ValueError, match="not valid YAML"):
            parse_import("yaml", "foods: [unclosed")

    def test_csv_types_and_blanks(self) -> None:
        rows, source = parse_import(
            "csv",
            CSV_HEADER
            + "pear,Pear ripe,fruit,60,g,34,0.2,0.1,9,0.1,5,0.06,,,,,2.7,1.9,"
            + "egg;soy,false,false,false,6,\n",
        )
        assert source is None
        [row] = rows
        assert row["serving_size"] == 60 and row["calories"] == 34 and row["fat_g"] == 0.1
        assert row["allergens"] == ["egg", "soy"] and row["choking_hazard"] is False
        assert row["min_age_months"] == 6 and row["source"] is None
        # Filled micronutrient cells coerce to numbers; blank ones stay absent (not zero).
        assert row["zinc_mg"] == 0.06 and row["vitamin_c_mg"] == 2.7 and row["fiber_g"] == 1.9
        for absent in ("vitamin_a_ug", "iodine_ug", "vitamin_b12_ug", "folate_ug"):
            assert absent not in row

    def test_csv_without_micronutrient_columns_still_imports(self) -> None:
        rows, _ = parse_import(
            "csv",
            LEGACY_CSV_HEADER
            + "pear,Pear ripe,fruit,60,g,34,0.2,0.1,9,0.1,5,egg;soy,false,false,false,6,\n",
        )
        [row] = rows
        assert row["calories"] == 34
        assert "zinc_mg" not in row and "fiber_g" not in row

    def test_size_cap_and_unknown_format(self) -> None:
        with pytest.raises(ValueError, match="KiB"):
            parse_import("yaml", "x" * (1_048_576 + 1))
        with pytest.raises(ValueError, match="unknown import format"):
            parse_import("xml", "<foods/>")


class TestPlanImport:
    def test_one_bad_row_blocks_the_file_and_is_named(self, table: FoodTable) -> None:
        rows = [
            PEAR,
            {**PEAR, "id": "plum", "name": "Plum", "iron_mg": -1},
            {**PEAR, "id": "kiwi", "name": "Kiwi"},
        ]
        plan = plan_import(table, rows, "upsert", None)
        assert plan.table is None and plan.created == []
        [error] = plan.errors
        assert (error.row, error.id, error.field) == (2, "plum", "iron_mg")
        assert "greater than or equal to 0" in error.message

    def test_bad_micronutrient_cell_fails_its_row(self, table: FoodTable) -> None:
        rows = [PEAR, {**PEAR, "id": "plum", "name": "Plum", "zinc_mg": -2}]
        plan = plan_import(table, rows, "upsert", None)
        assert plan.table is None and plan.created == []
        [error] = plan.errors
        assert (error.row, error.id, error.field) == (2, "plum", "zinc_mg")
        assert "greater than or equal to 0" in error.message

    def test_micronutrients_import_filled_and_blank(self, table: FoodTable) -> None:
        rows = [
            {**PEAR, "zinc_mg": 0.06, "vitamin_b12_ug": 0},
            {**LENTILS_ENTRY, "source": "test source", "folate_ug": 90},
        ]
        plan = plan_import(table, rows, "upsert", None)
        assert plan.errors == [] and plan.table is not None
        by_id = plan.table.by_id()
        pear = by_id["pear"]
        assert pear.zinc_mg == 0.06 and pear.vitamin_b12_ug == 0.0
        assert pear.iodine_ug is None  # not measured, never zero
        assert by_id["lentils"].folate_ug == 90

    def test_clean_file_reports_created_updated_unchanged(self, table: FoodTable) -> None:
        rows = [
            PEAR,  # new
            {**VALID_ENTRY, "calories": 50, "source": "s"},  # changed banana
            {**LENTILS_ENTRY, "source": "test source"},  # identical to the stored entry
        ]
        plan = plan_import(table, rows, "upsert", None)
        assert plan.errors == [] and plan.table is not None
        assert (plan.created, plan.updated, plan.unchanged) == (["pear"], ["banana"], ["lentils"])
        assert plan.changes_anything
        assert [f.id for f in plan.table.foods] == ["banana", "lentils", "breast_milk", "pear"]

    def test_file_source_fills_a_blank_row_source(self, table: FoodTable) -> None:
        plan = plan_import(table, [{**PEAR, "source": None}], "upsert", "USDA FDC")
        assert plan.errors == [] and plan.table.by_id()["pear"].source == "USDA FDC"
        without = plan_import(table, [{**PEAR, "source": None}], "upsert", None)
        assert without.errors[0].field == "source"

    def test_create_only_refuses_an_existing_id(self, table: FoodTable) -> None:
        plan = plan_import(table, [{**VALID_ENTRY, "source": "s"}], "create_only", None)
        assert plan.errors[0].message == "already exists" and plan.table is None

    def test_duplicate_ids_within_the_file_and_admin_rules_are_row_errors(
        self, table: FoodTable
    ) -> None:
        plan = plan_import(table, [PEAR, PEAR], "upsert", None)
        assert plan.errors[0].message == "listed twice in the file"
        plan = plan_import(
            table, [{**PEAR, "category": "milk_feed", "min_age_months": 0}], "upsert", None
        )
        assert "reserved" in plan.errors[0].message

    def test_unchanged_only_changes_nothing(self, table: FoodTable) -> None:
        plan = plan_import(table, [{**LENTILS_ENTRY, "source": "test source"}], "upsert", None)
        assert plan.unchanged == ["lentils"] and not plan.changes_anything
