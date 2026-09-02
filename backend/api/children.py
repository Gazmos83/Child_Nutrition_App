"""``/api/children`` -- the caller's child profiles, feeding logs, and growth logs (hard
rule 9).

Every route here runs behind ``CurrentUser`` or ``OwnedChild`` (``backend/api/deps.py``);
the list query is the only one that filters by ``user_id`` itself. ``to_child_context``
and ``to_feeding_entries`` are the read side of the authority seam: ``POST /api/chat``
builds its context from these rows and nowhere else. Age is derived from the stored date
of birth wherever it is read (hard rule 1; growth-tracking design Decision 1).
"""

import datetime as dt
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.api.deps import CurrentUser, DbSession, OwnedChild
from backend.models import ChildProfile, Feeding, GrowthMeasurement
from backend.models.enums import FeedingType
from backend.nutrition.feeding import (
    FeedingEntryError,
    daily_totals,
    group_by_day,
    normalise_entry,
)
from backend.nutrition.foods import FoodNotFoundError, get_food_table
from backend.nutrition.gaps import targets_with_intake
from backend.nutrition.growth import GROWTH_SOURCE, get_growth_table, get_reference_curves
from backend.rag.prompts import DISCLAIMER
from backend.schemas.chat import ChildContext
from backend.schemas.child import (
    AGE_OUT_OF_RANGE_DETAIL,
    ChildProfileResponse,
    ChildProfileWrite,
    DailyTargetsResponse,
    GrowthMeasurementResponse,
    GrowthMeasurementWrite,
)
from backend.schemas.tools import (
    MAX_AGE_MONTHS,
    MAX_LOG_ENTRIES,
    FeedingEntry,
    GrowthAssessmentInput,
    GrowthCurvesResponse,
    LoggedFeeding,
)
from backend.tools import nutrient_tools
from backend.tools.feeding_log import log_feeding
from backend.tools.targets_resolution import general_targets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/children", tags=["children"])

# Matches the client-held window the feeding-log spec bounded the log to.
DEFAULT_LOG_DAYS = 14
MAX_LOG_DAYS = 90


# -- mapping ---------------------------------------------------------------------------------


def _apply(profile: ChildProfile, body: ChildProfileWrite) -> None:
    profile.birth_date = body.birth_date
    profile.weight_kg = Decimal(str(body.weight_kg))
    profile.sex = body.sex
    profile.height_cm = Decimal(str(body.height_cm)) if body.height_cm is not None else None
    profile.diet_preference = body.diet_preference
    profile.activity_level = body.activity_level
    profile.allergens = sorted(body.allergies)
    # A note is dated when it changes (design.md Decision 9: both set or both null).
    if body.doctors_note != profile.doctors_note:
        profile.doctors_note = body.doctors_note
        profile.doctors_note_recorded_at = (
            dt.datetime.now(dt.UTC) if body.doctors_note is not None else None
        )


def to_response(profile: ChildProfile) -> ChildProfileResponse:
    return ChildProfileResponse(
        id=profile.id,
        birth_date=profile.birth_date,
        age_months=profile.age_months,
        weight_kg=float(profile.weight_kg),
        sex=profile.sex,
        height_cm=float(profile.height_cm) if profile.height_cm is not None else None,
        diet_preference=profile.diet_preference,
        allergies=sorted(profile.allergens),
        doctors_note=profile.doctors_note,
        doctors_note_recorded_at=profile.doctors_note_recorded_at,
        activity_level=profile.activity_level,
        created_at=profile.created_at,
    )


def to_child_context(profile: ChildProfile) -> ChildContext:
    """The stored profile as the context the chat and the tools take."""
    return ChildContext(
        age_months=profile.age_months,
        weight_kg=float(profile.weight_kg),
        sex=profile.sex,
        height_cm=float(profile.height_cm) if profile.height_cm is not None else None,
        diet_preference=profile.diet_preference,
        allergies=frozenset(profile.allergens),
        doctors_note=profile.doctors_note,
        activity_level=profile.activity_level,
    )


def child_context_or_422(profile: ChildProfile) -> ChildContext:
    """``to_child_context`` for a request: a child whose derived age has passed the supported
    range is refused with the range named, not failed (child-profile spec)."""
    if profile.age_months > MAX_AGE_MONTHS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=AGE_OUT_OF_RANGE_DETAIL)
    return to_child_context(profile)


def to_feeding_entry(row: Feeding) -> FeedingEntry:
    return FeedingEntry(
        id=str(row.id),
        fed_at=row.fed_at,
        feeding_type=row.feeding_type,
        food_id=row.food_id,
        quantity=float(row.quantity) if row.quantity is not None else None,
        unit=row.unit,  # type: ignore[arg-type]  # CHECK constraint limits it to ml | g
    )


async def recent_feedings(db: DbSession, child: ChildProfile, days: int) -> list[Feeding]:
    """The child's feeds from the last ``days`` days, newest first, bounded like the request."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    result = await db.execute(
        select(Feeding)
        .where(Feeding.child_profile_id == child.id, Feeding.fed_at >= since)
        .order_by(Feeding.fed_at.desc())
        .limit(MAX_LOG_ENTRIES)
    )
    return list(result.scalars())


def to_feeding_entries(rows: list[Feeding]) -> list[FeedingEntry]:
    return [to_feeding_entry(row) for row in rows]


def _price(entry: FeedingEntry) -> LoggedFeeding:
    try:
        return log_feeding(entry)
    except FoodNotFoundError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown food id {exc.food_id!r}: choose a food from /api/foods",
        ) from exc
    except FeedingEntryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


# -- profiles ---------------------------------------------------------------------------------


@router.get("", response_model=list[ChildProfileResponse], summary="The caller's children")
async def list_children(user: CurrentUser, db: DbSession) -> list[ChildProfileResponse]:
    result = await db.execute(
        select(ChildProfile)
        .where(ChildProfile.user_id == user.id)
        .order_by(ChildProfile.created_at)
    )
    return [to_response(profile) for profile in result.scalars()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ChildProfileResponse,
    summary="Add a child",
)
async def create_child(
    body: ChildProfileWrite, user: CurrentUser, db: DbSession
) -> ChildProfileResponse:
    profile = ChildProfile(user_id=user.id)
    _apply(profile, body)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return to_response(profile)


@router.get("/{child_id}", response_model=ChildProfileResponse, summary="One child")
async def get_child(child: OwnedChild) -> ChildProfileResponse:
    return to_response(child)


@router.put("/{child_id}", response_model=ChildProfileResponse, summary="Replace a child's details")
async def replace_child(
    body: ChildProfileWrite, child: OwnedChild, db: DbSession
) -> ChildProfileResponse:
    _apply(child, body)
    await db.commit()
    await db.refresh(child)
    return to_response(child)


@router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a child")
async def delete_child(child: OwnedChild, db: DbSession) -> None:
    """Removes the profile, its allergies, its feeding log, and its growth log (ON DELETE
    CASCADE)."""
    await db.delete(child)
    await db.commit()


@router.get(
    "/{child_id}/targets",
    response_model=DailyTargetsResponse,
    summary="The child's daily reference targets",
)
async def get_targets(child: OwnedChild, db: DbSession) -> DailyTargetsResponse:
    """The general reference targets for the stored profile, in display order, with the
    logged window's intake and flag on each tracked row (chat-ui spec).

    Deterministic: no language-model call and no doctor's-note extraction (day-9 design
    Decision 6) -- the note is disclosed and takes effect when meal plans are generated.
    ``OwnedChild`` resolves the profile only through the signed-in account's ownership, so
    a non-owner gets the same refusal as a direct profile read (hard rule 9).
    """
    targets = general_targets(child_context_or_422(child))
    table = get_food_table()
    normalised = []
    for row in await recent_feedings(db, child, DEFAULT_LOG_DAYS):
        try:
            normalised.append(normalise_entry(to_feeding_entry(row), table))
        except FoodNotFoundError, FeedingEntryError:
            # Same stance as the feeding list: a stored id the table no longer knows is
            # logged and skipped rather than failing the whole panel.
            logger.warning("Feeding %s names a food the table no longer has", row.id)
    daily = daily_totals(group_by_day(normalised, "UTC"))
    as_of = dt.datetime.now(dt.UTC).date()
    return DailyTargetsResponse(
        targets=targets_with_intake(daily, targets, as_of),
        diet_preference=child.diet_preference,
        doctors_note_present=child.doctors_note is not None,
        disclaimer=DISCLAIMER,
    )


# -- feeding log ------------------------------------------------------------------------------


@router.get(
    "/{child_id}/feedings",
    response_model=list[LoggedFeeding],
    summary="The child's recent feeds, priced against the food table",
)
async def list_feedings(
    child: OwnedChild,
    db: DbSession,
    days: int = Query(default=DEFAULT_LOG_DAYS, ge=1, le=MAX_LOG_DAYS),
) -> list[LoggedFeeding]:
    """Nutrients are recomputed from the committed table on every read, never stored."""
    table = get_food_table()
    priced: list[LoggedFeeding] = []
    for row in await recent_feedings(db, child, days):
        try:
            priced.append(log_feeding(to_feeding_entry(row), table))
        except FoodNotFoundError, FeedingEntryError:
            # The table is versioned and only grows, so this is a stored id the table no
            # longer knows -- surfaced in the log rather than failing the whole list.
            logger.warning("Feeding %s names a food the table no longer has", row.id)
    return priced


@router.post(
    "/{child_id}/feedings",
    status_code=status.HTTP_201_CREATED,
    response_model=LoggedFeeding,
    summary="Log one feed",
    responses={
        422: {"description": "The entry contradicts the food table (unknown food, wrong unit)."}
    },
)
async def create_feeding(entry: FeedingEntry, child: OwnedChild, db: DbSession) -> LoggedFeeding:
    """Validate and price the entry, then store it against the child.

    Idempotent on ``id``: the chat's ``log_feeding`` tool hands the browser an already
    identified entry, which is posted here afterwards; re-posting returns the stored row,
    even if the replayed body differs -- the first write is authoritative.
    """
    logged = _price(entry)
    try:
        feeding_id = uuid.UUID(logged.entry.id or "")
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="id must be a UUID"
        ) from exc
    existing = await db.get(Feeding, feeding_id)
    if existing is None:
        stored = logged.entry
        db.add(
            Feeding(
                id=feeding_id,
                child_profile_id=child.id,
                fed_at=stored.fed_at,
                feeding_type=FeedingType(stored.feeding_type),
                food_id=logged.food_id,
                quantity=Decimal(str(stored.quantity)) if stored.quantity is not None else None,
                unit=stored.unit,
            )
        )
        try:
            await db.commit()
            return logged
        except IntegrityError:
            # The same id landed concurrently (the browser saving a model-logged feed while
            # the parent re-posts it): fall through and answer with the stored row.
            await db.rollback()
            existing = await db.get(Feeding, feeding_id)
            if existing is None:
                raise
    if existing.child_profile_id != child.id:
        # An id the caller does not own: indistinguishable from a fresh collision.
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That entry id is taken")
    # The stored row wins over whatever the replayed body said; price it the same way.
    return _price(to_feeding_entry(existing))


@router.delete(
    "/{child_id}/feedings/{feeding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a logged feed",
)
async def delete_feeding(feeding_id: uuid.UUID, child: OwnedChild, db: DbSession) -> None:
    row = await db.get(Feeding, feeding_id)
    if row is None or row.child_profile_id != child.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such feeding")
    await db.delete(row)
    await db.commit()


# -- growth log -------------------------------------------------------------------------------

NO_SUCH_MEASUREMENT_DETAIL = "No such measurement"
MEASUREMENT_DAY_TAKEN_DETAIL = "A measurement for that day already exists"
MEASURED_PAST_RANGE_DETAIL = (
    f"measured_on puts the child past {MAX_AGE_MONTHS} months; the WHO standards stop there"
)
# Mean Gregorian month, for the plotting age only (growth-charts design Decision 3).
DAYS_PER_MONTH = 30.4375


def to_growth_response(child: ChildProfile, row: GrowthMeasurement) -> GrowthMeasurementResponse:
    """The stored row plus what is derived from it on every read: the age on that day and
    the WHO assessment (growth-tracking spec). Neither is ever stored.

    A row the stored birth date no longer covers (the date was moved after the measurement
    was logged) is returned with ``assessment=None`` rather than dropped: it is the parent's
    own record, and they can still see and delete it.
    """
    height_cm = float(row.height_cm) if row.height_cm is not None else None
    age_months, assessment = 0, None
    days_since_birth = max(0, (row.measured_on - child.birth_date).days)
    if child.birth_date <= row.measured_on:
        age_months = child.age_months_on(row.measured_on)
        if age_months <= MAX_AGE_MONTHS:
            assessment = nutrient_tools.assess_growth(
                GrowthAssessmentInput(
                    age_months=age_months,
                    sex=child.sex,
                    weight_kg=float(row.weight_kg),
                    height_cm=height_cm,
                )
            )
    if assessment is None:
        logger.warning("Growth measurement %s lies outside 0-60 months for the birth date", row.id)
    return GrowthMeasurementResponse(
        id=row.id,
        measured_on=row.measured_on,
        age_months=age_months,
        age_months_exact=round(days_since_birth / DAYS_PER_MONTH, 2),
        weight_kg=float(row.weight_kg),
        height_cm=height_cm,
        assessment=assessment,
        created_at=row.created_at,
    )


@router.get(
    "/{child_id}/growth",
    response_model=list[GrowthMeasurementResponse],
    summary="The child's growth measurements, newest first, placed on the WHO standards",
)
async def list_growth(child: OwnedChild, db: DbSession) -> list[GrowthMeasurementResponse]:
    """Age and assessment are recomputed from the birth date and the WHO table on every
    read, never stored -- the feeding log's stance on nutrients."""
    result = await db.execute(
        select(GrowthMeasurement)
        .where(GrowthMeasurement.child_profile_id == child.id)
        .order_by(GrowthMeasurement.measured_on.desc())
    )
    return [to_growth_response(child, row) for row in result.scalars()]


@router.get(
    "/{child_id}/growth/curves",
    response_model=GrowthCurvesResponse,
    summary="WHO percentile curves for the child's sex, 10th to 90th, per indicator",
)
async def growth_curves(child: OwnedChild) -> GrowthCurvesResponse:
    """Table arithmetic only (growth-charts design Decision 1); the child supplies the sex
    and whether the length or the height table applies. Owner-scoped like every child read."""
    return GrowthCurvesResponse(
        sex=child.sex,
        age_months=child.age_months,
        indicators=list(get_reference_curves(child.sex, child.age_months >= 24)),
        source=GROWTH_SOURCE,
        source_url=get_growth_table().source_url,
    )


@router.post(
    "/{child_id}/growth",
    status_code=status.HTTP_201_CREATED,
    response_model=GrowthMeasurementResponse,
    summary="Record one measurement",
    responses={
        422: {"description": "Dated before the birth date, past 60 months, or in the future."},
        409: {"description": "The child already has a measurement for that day."},
    },
)
async def create_growth(
    body: GrowthMeasurementWrite, child: OwnedChild, db: DbSession
) -> GrowthMeasurementResponse:
    """Store the measurement and, when it is the newest by date, carry its weight and any
    height onto the profile in the same transaction (growth-tracking design Decision 6).

    A missing height means "not measured today", so it never clears the profile's height.
    The ``(child, day)`` unique constraint turns a duplicate into a 409.
    """
    if body.measured_on < child.birth_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"measured_on is before the child's date of birth ({child.birth_date})",
        )
    if child.age_months_on(body.measured_on) > MAX_AGE_MONTHS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=MEASURED_PAST_RANGE_DETAIL
        )
    newest = await db.scalar(
        select(func.max(GrowthMeasurement.measured_on)).where(
            GrowthMeasurement.child_profile_id == child.id
        )
    )
    row = GrowthMeasurement(
        child_profile_id=child.id,
        measured_on=body.measured_on,
        weight_kg=Decimal(str(body.weight_kg)),
        height_cm=Decimal(str(body.height_cm)) if body.height_cm is not None else None,
    )
    db.add(row)
    if newest is None or body.measured_on >= newest:
        child.weight_kg = row.weight_kg
        if row.height_cm is not None:
            child.height_cm = row.height_cm
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=MEASUREMENT_DAY_TAKEN_DETAIL) from exc
    await db.refresh(row)
    await db.refresh(child)
    return to_growth_response(child, row)


@router.delete(
    "/{child_id}/growth/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a measurement",
)
async def delete_growth(measurement_id: uuid.UUID, child: OwnedChild, db: DbSession) -> None:
    """The profile keeps its weight and height (growth-tracking design Decision 6)."""
    row = await db.get(GrowthMeasurement, measurement_id)
    if row is None or row.child_profile_id != child.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_MEASUREMENT_DETAIL)
    await db.delete(row)
    await db.commit()
