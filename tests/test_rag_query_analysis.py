"""Deterministic age extraction (Day 3 task 5.2; advanced-rag-retrieval spec)."""

import pytest

from backend.rag.query_analysis import AgeRange, extract_age_range


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # Spec scenarios
        ("What can my 8-month-old eat?", (8, 8)),
        ("How much milk should a 2 year old drink?", (24, 35)),
        ("When can a toddler have peanut butter?", (12, 36)),
        ("What is fiber?", None),
        # Task 5.2 extras
        ("Is my 18 months old getting enough iron?", (18, 18)),
        ("Snacks for a 2-year-old", (24, 35)),
        ("My baby is 3 weeks old and spitting up", (0, 0)),
        ("How many calories does a 4 year old need?", (48, 59)),
        ("Diet for a 5 year old", (60, 60)),  # capped at the supported span
        ("School lunch for a 7 year old", None),  # entirely out of range
        # Forms
        ("Our 6 mo old refuses vegetables", (6, 6)),
        ("Feeding a two year old", (24, 35)),
        ("Is juice ok for a twelve-month-old?", (12, 12)),
        ("What should a 2 and a half year old eat?", (30, 30)),
        ("2.5 years old and not eating meat", (30, 30)),
        ("My son is 1 year 4 months", (16, 16)),
        ("Meal ideas for 6-12 months", (6, 12)),
        ("Iron for infants 7 to 12 months", (7, 12)),
        ("Portions for kids 2 to 3 years", (24, 47)),
        ("Newborn feeding schedule", (0, 1)),
        ("Vitamin D for a neonate", (0, 1)),
        ("Healthy snacks for preschoolers", (36, 60)),
        ("Is honey safe for infants?", (0, 12)),
        ("Can babies have strawberries", (0, 12)),
        # Numeric age wins over a stage word
        ("My toddler is 30 months and won't drink milk", (30, 30)),
        # Accepted false positive (documented in module docstring)
        ("6 months ago I stopped breastfeeding; what now?", (6, 6)),
        ("", None),
        ("How much protein in an egg?", None),
    ],
)
def test_extract_age_range(question: str, expected: tuple[int, int] | None) -> None:
    result = extract_age_range(question)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert (result.min_months, result.max_months) == expected


def test_age_range_is_validated_and_immutable() -> None:
    with pytest.raises(ValueError):
        AgeRange(min_months=10, max_months=5)
    with pytest.raises(ValueError):
        AgeRange(min_months=0, max_months=61)
    r = AgeRange(min_months=8, max_months=8)
    assert r.is_exact
    with pytest.raises(ValueError):
        r.min_months = 9  # type: ignore[misc]
