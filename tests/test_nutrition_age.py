"""Completed months from a date of birth (growth-tracking design Decision 2)."""

import datetime as dt

import pytest

from backend.nutrition.age import DATE_TOLERANCE, birth_date_for, completed_months, today


class TestCompletedMonths:
    @pytest.mark.parametrize(
        ("birth", "as_of", "expected"),
        [
            # Born on the 31st: the anniversary clamps to the last day of a shorter month.
            (dt.date(2025, 1, 31), dt.date(2025, 2, 28), 1),
            (dt.date(2024, 1, 31), dt.date(2024, 2, 29), 1),
            (dt.date(2025, 1, 31), dt.date(2025, 3, 30), 1),
            (dt.date(2025, 1, 31), dt.date(2025, 3, 31), 2),
            # Born on a leap day.
            (dt.date(2024, 2, 29), dt.date(2025, 2, 27), 11),
            (dt.date(2024, 2, 29), dt.date(2025, 2, 28), 12),
            (dt.date(2024, 2, 29), dt.date(2025, 3, 1), 12),
            # Ordinary cases and boundaries.
            (dt.date(2026, 1, 10), dt.date(2026, 1, 10), 0),
            (dt.date(2026, 1, 10), dt.date(2026, 5, 9), 3),
            (dt.date(2026, 1, 10), dt.date(2026, 5, 10), 4),
            (dt.date(2021, 9, 2), dt.date(2026, 9, 2), 60),
            (dt.date(2021, 9, 3), dt.date(2026, 9, 2), 59),
        ],
    )
    def test_calendar_month_arithmetic(self, birth: dt.date, as_of: dt.date, expected: int):
        assert completed_months(birth, as_of) == expected

    def test_day_before_birth_raises(self) -> None:
        with pytest.raises(ValueError, match="before the date of birth"):
            completed_months(dt.date(2026, 1, 10), dt.date(2026, 1, 9))


class TestBirthDateFor:
    @pytest.mark.parametrize(
        "as_of",
        [dt.date(2026, 9, 2), dt.date(2026, 1, 31), dt.date(2024, 2, 29), dt.date(2026, 3, 31)],
    )
    def test_round_trips_through_completed_months(self, as_of: dt.date) -> None:
        for months in range(0, 61):
            birth = birth_date_for(months, as_of)
            assert completed_months(birth, as_of) == months, (months, as_of, birth)

    def test_is_the_latest_such_date(self) -> None:
        as_of = dt.date(2026, 9, 2)
        birth = birth_date_for(8, as_of)
        assert birth == dt.date(2026, 1, 2)
        assert completed_months(birth + dt.timedelta(days=1), as_of) == 7

    def test_negative_months_rejected(self) -> None:
        with pytest.raises(ValueError):
            birth_date_for(-1, dt.date(2026, 9, 2))


def test_today_is_a_date_and_tolerance_is_one_day() -> None:
    assert isinstance(today(), dt.date)
    assert DATE_TOLERANCE.days == 1
