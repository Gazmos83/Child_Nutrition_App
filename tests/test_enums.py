"""Controlled vocabulary guarantees (tasks 4.1, 4.2, 4.3).

Hard rule 2: allergies and diet preference are controlled vocabularies, never free text.
"""

import re
from enum import StrEnum

import pytest

from backend.models.enums import Allergen, DietPreference, FeedingType, Sex

ALL_VOCABULARIES: list[type[StrEnum]] = [Sex, DietPreference, Allergen, FeedingType]

# PostgreSQL enum labels are created from these values. Constraining them to lowercase
# snake_case keeps labels stable and quoting-free across migrations.
STABLE_LABEL = re.compile(r"^[a-z][a-z0-9_]*$")

# The regulatory "big nine" major food allergens (FASTER Act 2021 added sesame).
BIG_NINE = {
    "milk",
    "egg",
    "peanut",
    "tree_nut",
    "soy",
    "wheat",
    "fish",
    "shellfish",
    "sesame",
}


class TestVocabularyCoverage:
    def test_allergen_covers_exactly_the_big_nine(self) -> None:
        assert {a.value for a in Allergen} == BIG_NINE

    def test_allergen_has_no_none_sentinel(self) -> None:
        # "No allergies" is the empty association set, not a storable member.
        # A NONE member could otherwise be persisted *alongside* a real allergen.
        values = {a.value for a in Allergen}
        assert values.isdisjoint({"none", "null", "unknown", "other", "n/a"})

    def test_sex_covers_growth_standard_values(self) -> None:
        assert {s.value for s in Sex} == {"male", "female"}

    def test_diet_preference_members(self) -> None:
        assert {d.value for d in DietPreference} == {
            "omnivore",
            "vegetarian",
            "pescatarian",
            "vegan",
        }

    def test_feeding_type_members(self) -> None:
        assert {f.value for f in FeedingType} == {"breastmilk", "formula", "solid", "water"}


class TestDietPreferenceDefault:
    """Task 4.2 / spec scenario: unspecified preference has a defined default."""

    def test_default_is_a_real_member(self) -> None:
        default = DietPreference.default()
        assert default is not None
        assert isinstance(default, DietPreference)
        assert default in list(DietPreference)

    def test_default_is_omnivore(self) -> None:
        assert DietPreference.default() is DietPreference.OMNIVORE


class TestLabelStability:
    """Task 4.3: members must be stable, lowercase PostgreSQL enum labels."""

    @pytest.mark.parametrize("vocabulary", ALL_VOCABULARIES, ids=lambda v: v.__name__)
    def test_all_values_are_lowercase(self, vocabulary: type[StrEnum]) -> None:
        for member in vocabulary:
            assert member.value == member.value.lower(), f"{vocabulary.__name__}.{member.name}"

    @pytest.mark.parametrize("vocabulary", ALL_VOCABULARIES, ids=lambda v: v.__name__)
    def test_all_values_are_stable_labels(self, vocabulary: type[StrEnum]) -> None:
        for member in vocabulary:
            assert STABLE_LABEL.match(member.value), (
                f"{vocabulary.__name__}.{member.name} = {member.value!r} is not a "
                "stable snake_case PostgreSQL enum label"
            )

    @pytest.mark.parametrize("vocabulary", ALL_VOCABULARIES, ids=lambda v: v.__name__)
    def test_values_are_unique(self, vocabulary: type[StrEnum]) -> None:
        values = [m.value for m in vocabulary]
        assert len(values) == len(set(values))


class TestFreeTextRejection:
    """Hard rule 2 at the Python boundary; the DB enum enforces it again on Day 7."""

    @pytest.mark.parametrize("bad", ["Peanuts", "peanut butter", "PEANUT", "", "cashew"])
    def test_off_vocabulary_allergen_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Allergen(bad)

    @pytest.mark.parametrize("bad", ["no dairy", "Vegan", "keto", ""])
    def test_off_vocabulary_diet_preference_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            DietPreference(bad)

    @pytest.mark.parametrize("bad", ["Breastmilk", "bottle", "snack", ""])
    def test_off_vocabulary_feeding_type_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            FeedingType(bad)
