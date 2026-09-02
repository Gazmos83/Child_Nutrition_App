"""Avoidance phrases resolve to categories or foods in code, never by guessing
(child-notes-restrictions design Decision 5)."""

from pathlib import Path

import pytest

from backend.chat import copy
from backend.models.enums import NoteKind
from backend.nutrition.avoidance import (
    CATEGORY_ALIASES,
    filter_by_avoidances,
    resolve_avoidance,
)
from backend.nutrition.foods import FoodCategory, LoadedFoodTable, load_food_table
from backend.schemas.tools import ExtractedAvoidance

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def table() -> LoadedFoodTable:
    return load_food_table()


def phrase(text: str, index: int = 0) -> ExtractedAvoidance:
    return ExtractedAvoidance(note_index=index, phrase=text)


class TestResolveAvoidance:
    def test_named_food_resolves_to_its_entry(self, table: LoadedFoodTable) -> None:
        result = resolve_avoidance(phrase("iron fortified oat cereal"), NoteKind.DOCTOR, table)
        assert result.applied and result.food_ids == ["infant_cereal_iron_fortified"]
        assert result.category is None and result.kind is NoteKind.DOCTOR
        assert result.detail == copy.avoidance_applied("iron fortified oat cereal", 1)

    @pytest.mark.parametrize("spoken", ["dairy", "Dairy products", "milk products"])
    def test_category_and_aliases_exclude_the_group_not_the_milk_feed(
        self, table: LoadedFoodTable, spoken: str
    ) -> None:
        result = resolve_avoidance(phrase(spoken), NoteKind.PREFERENCE, table)
        assert result.applied and result.category == "dairy"
        assert set(result.food_ids) == {
            f.id for f in table.foods if f.category is FoodCategory.DAIRY
        }
        assert "infant_formula_iron_fortified" not in result.food_ids

    def test_eggs_means_the_egg_category(self, table: LoadedFoodTable) -> None:
        result = resolve_avoidance(phrase("eggs"), NoteKind.PREFERENCE, table)
        assert result.category == "egg" and result.food_ids == ["egg_scrambled"]

    def test_ambiguous_phrase_excludes_every_candidate(self, table: LoadedFoodTable) -> None:
        result = resolve_avoidance(phrase("apple"), NoteKind.PREFERENCE, table)
        assert result.applied
        assert set(result.food_ids) == {"apple_cooked", "raw_apple_chunks", "unpasteurized_juice"}

    def test_milk_feeds_are_never_avoided(self, table: LoadedFoodTable) -> None:
        result = resolve_avoidance(phrase("breast milk"), NoteKind.DOCTOR, table)
        assert result.applied is False and result.food_ids == []
        assert result.detail == copy.NOTE_MILK_FEED
        # "milk" names a milk feed and dairy foods: the dairy foods go, the milk feed stays.
        mixed = resolve_avoidance(phrase("milk"), NoteKind.DOCTOR, table)
        assert mixed.applied and "breast_milk" not in mixed.food_ids
        assert "whole_cows_milk" in mixed.food_ids
        assert copy.NOTE_MILK_FEED in mixed.detail  # the row is told the milk feed stayed

    def test_unknown_phrase_is_not_applied_with_the_reason(self, table: LoadedFoodTable) -> None:
        result = resolve_avoidance(phrase("kale chips"), NoteKind.PREFERENCE, table)
        assert result.applied is False and result.food_ids == []
        assert result.detail == copy.note_no_match("kale chips")

    def test_aliases_never_name_milk_feeds(self) -> None:
        assert FoodCategory.MILK_FEED not in CATEGORY_ALIASES.values()
        assert CATEGORY_ALIASES["nuts"] is FoodCategory.NUT_SEED
        assert CATEGORY_ALIASES["sugar"] is FoodCategory.SWEETENER


class TestMatches:
    def test_matches_returns_all_candidates_and_nothing_for_unknown(
        self, table: LoadedFoodTable
    ) -> None:
        assert {f.id for f in table.matches("carrot")} == {
            "carrot_cooked_mashed",
            "raw_carrot_sticks",
        }
        assert [f.id for f in table.matches("avocado")] == ["avocado"]
        assert table.matches("kale chips") == []
        assert table.matches("banana mashd") == []  # no difflib guessing here


class TestFilterByAvoidances:
    def test_a_food_hit_by_two_rows_collects_two_reasons(self, table: LoadedFoodTable) -> None:
        pork = resolve_avoidance(phrase("pork", 0), NoteKind.DOCTOR, table)
        meat = resolve_avoidance(phrase("meat", 1), NoteKind.PREFERENCE, table)
        unmatched = resolve_avoidance(phrase("kale chips", 2), NoteKind.PREFERENCE, table)
        kept, excluded = filter_by_avoidances(
            table.foods, [pork, meat, unmatched], reason_for=lambda a: f"row {a.note_index}"
        )
        reasons = {food.id: reasons for food, reasons in excluded}
        assert reasons["pork_tenderloin_cooked"] == ["row 0", "row 1"]
        assert reasons["beef_ground_cooked"] == ["row 1"]
        assert "pork_tenderloin_cooked" not in {f.id for f in kept}
        assert len(kept) + len(excluded) == len(table.foods)


def test_no_langchain_import_under_nutrition() -> None:
    hits = [
        path
        for path in (REPO_ROOT / "backend" / "nutrition").glob("*.py")
        if "langchain" in path.read_text(encoding="utf-8")
    ]
    assert hits == []
