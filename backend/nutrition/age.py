"""Age from a date of birth, in completed months (hard rule 1; growth-tracking design
Decision 2).

The one place "today" is defined and the one place a calendar-month difference is
computed, so the profile's age, a measurement's age, and the write validators agree.
Standard library only, like the rest of ``backend.nutrition``.
"""

import calendar
import datetime as dt

# "Today" is the UTC date. A parent east of UTC is already on tomorrow's date for part of
# every day, so dates are accepted up to this far ahead and a derived age is clamped at 0.
DATE_TOLERANCE = dt.timedelta(days=1)


def today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def completed_months(birth_date: dt.date, as_of: dt.date) -> int:
    """Whole calendar months from ``birth_date`` to ``as_of``.

    A birthday on a day the month of ``as_of`` does not have (the 31st in April, the 29th
    in a non-leap February) counts as that month's last day -- the same convention as
    PostgreSQL's ``date - interval 'N months'``, which the migration backfill relies on.
    """
    if as_of < birth_date:
        raise ValueError(f"as_of {as_of} is before the date of birth {birth_date}")
    months = (as_of.year - birth_date.year) * 12 + (as_of.month - birth_date.month)
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    anniversary_day = min(birth_date.day, days_in_month)
    return months - 1 if as_of.day < anniversary_day else months


def birth_date_for(months: int, as_of: dt.date) -> dt.date:
    """The latest date of birth that gives exactly ``months`` completed months on ``as_of``.

    The inverse of :func:`completed_months` for tests and the evaluation harness, which
    describe children in months.
    """
    if months < 0:
        raise ValueError("months must not be negative")
    year, month = divmod(as_of.year * 12 + (as_of.month - 1) - months, 12)
    month += 1
    day = min(as_of.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)
