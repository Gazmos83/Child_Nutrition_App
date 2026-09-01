"""Nutrient-gap detection: widening rolling windows over complete days (change 2 design
Decision 6; nutrient-gap-detection spec).

Every clause of the reference's §9b table is a constant or a ``WINDOWS`` row here. The
function has no I/O: its tests are tables of daily totals and expected reports.
"""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

from backend.nutrition.feeding import DayTotals
from backend.nutrition.nutrients import SPECS
from backend.schemas.tools import (
    GapConfidence,
    GapFlag,
    NutrientGap,
    NutrientGapReport,
    NutrientTargets,
)

GAP_BELOW = 0.80  # ratio under this is "below"
GAP_ABOVE = 1.20  # ratio over this is "above"
LOOKBACK_DAYS = 14  # complete days are counted within this many days before the reference day

# (minimum complete days, window in days or None for "all available", confidence)
WINDOWS: tuple[tuple[int, int | None, GapConfidence], ...] = (
    (7, 7, "high"),
    (3, 3, "medium"),
    (1, None, "low"),
)


def _flag(ratio: float) -> GapFlag:
    if ratio < GAP_BELOW:
        return "below"
    if ratio > GAP_ABOVE:
        return "above"
    return "adequate"


@dataclass(frozen=True, slots=True)
class WindowSelection:
    """Which complete days a gap report averages over, and how confidently."""

    recent: tuple[DayTotals, ...]
    days_logged: int
    window_days: int
    partial_days: int
    confidence: GapConfidence | None
    """``None`` means insufficient data: no complete day in range."""


def select_window(daily: Mapping[dt.date, DayTotals], as_of: dt.date) -> WindowSelection:
    """The §9b window rule, reusable outside the report (e.g. the targets endpoint).

    Days strictly before ``as_of`` and within ``LOOKBACK_DAYS`` count; the reference day
    itself is never in the window (lunch has not happened yet). Days with an unmeasured
    feed are excluded and counted as ``partial_days``.
    """
    earliest = as_of - dt.timedelta(days=LOOKBACK_DAYS)
    in_range = [d for d in daily.values() if earliest <= d.date < as_of and d.entries > 0]
    complete = sorted((d for d in in_range if d.complete), key=lambda d: d.date, reverse=True)
    partial_days = sum(1 for d in in_range if not d.complete)
    days_logged = len(complete)

    if days_logged == 0:
        return WindowSelection(
            recent=(),
            days_logged=0,
            window_days=0,
            partial_days=partial_days,
            confidence=None,
        )

    _, window, confidence = next(row for row in WINDOWS if days_logged >= row[0])
    window_days = window or days_logged
    return WindowSelection(
        recent=tuple(complete[:window_days]),
        days_logged=days_logged,
        window_days=window_days,
        partial_days=partial_days,
        confidence=confidence,
    )


def targets_with_intake(
    daily: Mapping[dt.date, DayTotals], targets: NutrientTargets, as_of: dt.date
) -> NutrientTargets:
    """The target set with window-average intake and flags on the tracked rows.

    The targets endpoint's read side of the same §9b window rule the gap report uses: with
    no complete day in range the set is returned untouched, so a profile with no logged
    days carries no flags. Rows that are not tracked are never given intake (their
    validators forbid it), which is what keeps vitamin D unflagged by construction.
    """
    selection = select_window(daily, as_of)
    if selection.confidence is None:
        return targets
    rows = []
    for row in targets.items:
        if not row.tracked:
            rows.append(row)
            continue
        field = SPECS[row.nutrient].intake_field
        assert field is not None  # tracked_for() requires a declared intake field
        assert row.amount is not None  # a tracked row always has a numeric target
        average = sum(getattr(d.totals, field) for d in selection.recent) / selection.window_days
        ratio = round(average / row.amount, 2) if row.amount > 0 else 0.0
        rows.append(
            row.model_copy(
                update={"intake_average": round(average, 1), "ratio": ratio, "flag": _flag(ratio)}
            )
        )
    return NutrientTargets(items=tuple(rows))


def compute_gap_report(
    daily: Mapping[dt.date, DayTotals], targets: NutrientTargets, as_of: dt.date
) -> NutrientGapReport:
    """Compare window averages with the child's targets (window rule: ``select_window``)."""
    selection = select_window(daily, as_of)
    if selection.confidence is None:
        return NutrientGapReport(
            status="insufficient_data",
            days_logged=0,
            window_days=0,
            partial_days=selection.partial_days,
            as_of=as_of,
            targets=targets,
        )

    recent, window_days = selection.recent, selection.window_days

    # The flagged set is whatever the target set declares trackable for this child
    # (design Decision 3): a display-only row cannot reach a flag by construction.
    gaps: list[NutrientGap] = []
    for row in targets.tracked():
        field = SPECS[row.nutrient].intake_field
        assert field is not None  # tracked_for() requires a declared intake field
        assert row.amount is not None  # a tracked row always has a numeric target
        average = sum(getattr(d.totals, field) for d in recent) / window_days
        ratio = round(average / row.amount, 2) if row.amount > 0 else 0.0
        gaps.append(
            NutrientGap(
                nutrient=row.nutrient,
                label=row.label,
                unit=row.unit,
                average=round(average, 1),
                target=row.amount,
                ratio=ratio,
                flag=_flag(ratio),
                target_source=row.source,
                target_band=row.band,
            )
        )
    return NutrientGapReport(
        status="ok",
        confidence=selection.confidence,
        directional=selection.confidence == "low",
        days_logged=selection.days_logged,
        window_days=window_days,
        partial_days=selection.partial_days,
        as_of=as_of,
        gaps=gaps,
        targets=targets,
    )
