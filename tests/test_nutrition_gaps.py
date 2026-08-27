"""Gap detection: days in, report out (change 2 task 1.4; nutrient-gap-detection spec)."""

from datetime import date, timedelta

import pytest

from backend.nutrition.feeding import DayTotals
from backend.nutrition.gaps import GAP_ABOVE, GAP_BELOW, LOOKBACK_DAYS, compute_gap_report
from backend.schemas.tools import (
    CalorieTargetResult,
    IronTargetResult,
    NutrientTargets,
    NutrientTotals,
    ProteinTargetResult,
)

AS_OF = date(2026, 8, 27)
TARGETS = NutrientTargets(
    calories=CalorieTargetResult(calories=750, band="7–12 months", formula="test", source="DRI"),
    protein=ProteinTargetResult(
        protein_g=11.0, grams_per_kg=1.2, reference_type="RDA", band="7–12 months", source="DRI"
    ),
    iron=IronTargetResult(iron_mg=11.0, reference_type="RDA", band="7–12 months", source="DRI"),
)


def totals(calories: float, protein: float = 11.0, iron: float = 11.0) -> NutrientTotals:
    return NutrientTotals(
        calories=calories, protein_g=protein, fat_g=0, carbohydrate_g=0, iron_mg=iron, calcium_mg=0
    )


def day(days_ago: int, calories: float = 750, *, partial: bool = False, **kw) -> DayTotals:
    return DayTotals(
        date=AS_OF - timedelta(days=days_ago),
        totals=totals(calories, **kw),
        entries=2,
        unquantified=1 if partial else 0,
    )


def report(*days: DayTotals):
    return compute_gap_report({d.date: d for d in days}, TARGETS, AS_OF)


class TestWindows:
    def test_no_complete_days_is_insufficient_and_counts_partial(self) -> None:
        r = report(day(1, partial=True), day(2, partial=True))
        assert r.status == "insufficient_data"
        assert r.confidence is None and r.gaps == []
        assert r.days_logged == 0 and r.window_days == 0 and r.partial_days == 2
        assert r.as_of == AS_OF and r.targets == TARGETS

    def test_two_days_low_confidence_directional(self) -> None:
        r = report(day(1), day(2))
        assert r.status == "ok" and r.confidence == "low" and r.directional
        assert r.days_logged == 2 and r.window_days == 2

    def test_four_days_medium_uses_three_most_recent(self) -> None:
        # Oldest day is far below target; it must not enter the three-day window.
        r = report(day(1, 750), day(2, 750), day(3, 750), day(4, 75))
        assert r.confidence == "medium" and not r.directional
        assert r.days_logged == 4 and r.window_days == 3
        assert next(g for g in r.gaps if g.nutrient == "calories").average == 750.0

    def test_nine_days_high_uses_seven(self) -> None:
        r = report(*(day(i, 750) for i in range(1, 8)), day(8, 75), day(9, 75))
        assert r.confidence == "high" and r.window_days == 7 and r.days_logged == 9
        assert next(g for g in r.gaps if g.nutrient == "calories").flag == "adequate"

    def test_reference_day_excluded(self) -> None:
        r = report(day(0, 75), day(1), day(2))
        assert r.days_logged == 2
        assert all(g.flag == "adequate" for g in r.gaps)

    def test_day_fifteen_back_excluded(self) -> None:
        r = report(day(LOOKBACK_DAYS + 1, 75), day(LOOKBACK_DAYS, 75), day(1, 750))
        assert r.days_logged == 2  # day 14 counts, day 15 does not
        assert next(g for g in r.gaps if g.nutrient == "calories").average == 412.5

    def test_partial_days_excluded_but_counted(self) -> None:
        r = report(day(1), day(2, 75, partial=True), day(3))
        assert r.days_logged == 2 and r.partial_days == 1
        assert next(g for g in r.gaps if g.nutrient == "calories").flag == "adequate"


class TestFlags:
    @pytest.mark.parametrize(
        ("calories", "flag"),
        [(750 * 0.79, "below"), (750 * GAP_BELOW, "adequate"), (750 * GAP_ABOVE + 7.5, "above")],
    )
    def test_threshold_boundaries(self, calories: float, flag: str) -> None:
        r = report(day(1, calories), day(2, calories), day(3, calories))
        gap = next(g for g in r.gaps if g.nutrient == "calories")
        assert gap.flag == flag
        assert gap.ratio == round(calories / 750, 2)

    def test_exactly_one_point_two_is_adequate(self) -> None:
        r = report(day(1, 900), day(2, 900), day(3, 900))
        assert next(g for g in r.gaps if g.nutrient == "calories").flag == "adequate"

    def test_every_gap_carries_target_source_and_band(self) -> None:
        r = report(day(1, 600, protein=6.0, iron=14.0))
        assert {g.nutrient for g in r.gaps} == {"calories", "protein", "iron"}
        for gap in r.gaps:
            assert gap.target_source == "DRI" and gap.target_band == "7–12 months"
        by_name = {g.nutrient: g for g in r.gaps}
        assert by_name["calories"].unit == "kcal" and by_name["protein"].unit == "g"
        assert by_name["iron"].flag == "above" and by_name["protein"].flag == "below"

    def test_identical_inputs_identical_report(self) -> None:
        days = (day(1, 640), day(2, 660), day(3, 700))
        assert report(*days) == report(*days)
