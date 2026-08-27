"""Nutrient-gap detection: widening rolling windows over complete days (change 2 design
Decision 6; nutrient-gap-detection spec).

Every clause of the reference's §9b table is a constant or a ``WINDOWS`` row here. The
function has no I/O: its tests are tables of daily totals and expected reports.
"""

import datetime as dt
from collections.abc import Mapping

from backend.nutrition.feeding import DayTotals
from backend.schemas.tools import (
    GapConfidence,
    GapFlag,
    GapNutrient,
    NutrientGap,
    NutrientGapReport,
    NutrientTargets,
    NutrientUnit,
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

# (report nutrient, NutrientTotals field, unit)
_NUTRIENTS: tuple[tuple[GapNutrient, str, NutrientUnit], ...] = (
    ("calories", "calories", "kcal"),
    ("protein", "protein_g", "g"),
    ("iron", "iron_mg", "mg"),
)


def _target(targets: NutrientTargets, nutrient: GapNutrient) -> tuple[float, str, str]:
    if nutrient == "calories":
        return float(targets.calories.calories), targets.calories.source, targets.calories.band
    if nutrient == "protein":
        return targets.protein.protein_g, targets.protein.source, targets.protein.band
    return targets.iron.iron_mg, targets.iron.source, targets.iron.band


def _flag(ratio: float) -> GapFlag:
    if ratio < GAP_BELOW:
        return "below"
    if ratio > GAP_ABOVE:
        return "above"
    return "adequate"


def compute_gap_report(
    daily: Mapping[dt.date, DayTotals], targets: NutrientTargets, as_of: dt.date
) -> NutrientGapReport:
    """Compare window averages with the child's targets.

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
        return NutrientGapReport(
            status="insufficient_data",
            days_logged=0,
            window_days=0,
            partial_days=partial_days,
            as_of=as_of,
            targets=targets,
        )

    _, window, confidence = next(row for row in WINDOWS if days_logged >= row[0])
    window_days = window or days_logged
    recent = complete[:window_days]

    gaps: list[NutrientGap] = []
    for nutrient, field, unit in _NUTRIENTS:
        average = sum(getattr(d.totals, field) for d in recent) / window_days
        target, source, band = _target(targets, nutrient)
        ratio = round(average / target, 2) if target > 0 else 0.0
        gaps.append(
            NutrientGap(
                nutrient=nutrient,
                unit=unit,
                average=round(average, 1),
                target=target,
                ratio=ratio,
                flag=_flag(ratio),
                target_source=source,
                target_band=band,
            )
        )
    return NutrientGapReport(
        status="ok",
        confidence=confidence,
        directional=confidence == "low",
        days_logged=days_logged,
        window_days=window_days,
        partial_days=partial_days,
        as_of=as_of,
        gaps=gaps,
        targets=targets,
    )
