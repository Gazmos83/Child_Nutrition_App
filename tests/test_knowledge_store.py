"""SearchFilter validation and Document metadata (Day 3 task 2.2)."""

import pytest
from pydantic import ValidationError

from backend.db.knowledge_store import (
    AUTHORITIES,
    MAX_AGE_MONTHS,
    MIN_AGE_MONTHS,
    Document,
    SearchFilter,
)


class TestSearchFilterValidation:
    """Filters are built from validated ints and enum values only (design Decision 5)."""

    @pytest.mark.parametrize("age", [-1, 61, 120])
    def test_age_outside_0_60_is_rejected(self, age: int) -> None:
        with pytest.raises(ValidationError):
            SearchFilter(age_min_months=age)
        with pytest.raises(ValidationError):
            SearchFilter(age_max_months=age)

    def test_min_greater_than_max_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            SearchFilter(age_min_months=12, age_max_months=6)

    @pytest.mark.parametrize("bad", ["who", "Mayo Clinic", "WHO; drop table", ""])
    def test_unknown_authority_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            SearchFilter(authorities=(bad,))

    def test_free_text_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchFilter(expr='document_id == "x"')

    def test_vocabulary_matches_design(self) -> None:
        assert set(AUTHORITIES) == {"WHO", "AAP", "CDC", "USDA/HHS", "NIH", "FDA/EPA"}
        assert (MIN_AGE_MONTHS, MAX_AGE_MONTHS) == (0, 60)


class TestSearchFilterSemantics:
    def test_single_bound_means_exact_age(self) -> None:
        assert SearchFilter(age_min_months=8).age_max_months == 8
        assert SearchFilter(age_max_months=8).age_min_months == 8

    def test_empty_filter(self) -> None:
        f = SearchFilter()
        assert f.is_empty and not f.has_age

    def test_without_age_keeps_authorities(self) -> None:
        f = SearchFilter(age_min_months=6, age_max_months=8, authorities=("WHO", "AAP"))
        g = f.without_age()
        assert not g.has_age
        assert g.authorities == ("WHO", "AAP")

    def test_filter_is_immutable(self) -> None:
        f = SearchFilter(age_min_months=6)
        with pytest.raises(ValidationError):
            f.age_min_months = 7  # type: ignore[misc]


class TestDocumentMetadata:
    def test_age_range_defaults_to_full_span(self) -> None:
        doc = Document(content="x", source="s")
        assert (doc.age_min_months, doc.age_max_months) == (0, 60)
        assert doc.chunk_index == 0
        assert doc.embedding is None

    def test_embedding_is_not_in_repr(self) -> None:
        doc = Document(content="x", source="s", embedding=[0.1] * 4)
        assert "0.1" not in repr(doc)
