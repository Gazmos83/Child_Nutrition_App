"""``detect_nutrient_gaps``: logged intake against the child's targets over widening
windows (nutrient-gap-detection spec; change 2 design Decisions 5, 6, 8).

Async for the same reason the planner is: the targets come from ``resolve_targets``, which
may await the chat model to read a doctor's note. Everything after that is arithmetic in
``backend.nutrition``. Every call, including ``insufficient_data``, emits one JSON audit
line on ``backend.tools.audit``.
"""

import datetime as dt
import json
import logging
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel

from backend.nutrition.feeding import daily_totals, group_by_day, normalise_entries
from backend.nutrition.foods import LoadedFoodTable, get_food_table
from backend.nutrition.gaps import compute_gap_report
from backend.schemas.tools import GapDetectionRequest, NutrientGapReport
from backend.tools.targets_resolution import resolve_targets

audit_logger = logging.getLogger("backend.tools.audit")


def _audit(request: GapDetectionRequest, report: NutrientGapReport) -> None:
    record = {
        "event": "nutrient_gaps",
        "status": report.status,
        "input": {
            "age_months": request.age_months,
            "weight_kg": request.weight_kg,
            "height_cm": request.height_cm,
            "sex": request.sex.value,
            "notes": [row.model_dump(mode="json") for row in request.notes],
            "activity_level": request.activity_level.value,
            "entries": len(request.entries),
            "timezone": request.timezone,
        },
        "as_of": report.as_of.isoformat(),
        "days_logged": report.days_logged,
        "partial_days": report.partial_days,
        "window_days": report.window_days,
        "confidence": report.confidence,
        "directional": report.directional,
        "gaps": [g.model_dump(mode="json") for g in report.gaps],
        "note_extraction": (
            report.note_extraction.model_dump(mode="json") if report.note_extraction else None
        ),
        "overrides": (
            [o.model_dump(mode="json") for o in report.overrides]
            if report.overrides is not None
            else None
        ),
    }
    audit_logger.info("nutrient_gaps_audit %s", json.dumps(record, sort_keys=True))


async def detect_nutrient_gaps(
    request: GapDetectionRequest,
    chat_model: BaseChatModel | None,
    table: LoadedFoodTable | None = None,
) -> NutrientGapReport:
    """Normalise -> group by local day -> resolve targets -> compare windows -> audit."""
    table = table or get_food_table()
    targets, extraction, overrides = await resolve_targets(request, chat_model)
    daily = daily_totals(group_by_day(normalise_entries(request.entries, table), request.timezone))
    as_of = request.as_of or dt.datetime.now(ZoneInfo(request.timezone)).date()
    report = compute_gap_report(daily, targets, as_of).model_copy(
        update={"note_extraction": extraction, "overrides": overrides}
    )
    _audit(request, report)
    return report
