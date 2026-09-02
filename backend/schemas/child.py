"""Request and response models for ``/api/children`` (child-profile and growth-tracking
specs).

The write model shares its field definitions with ``ChildContext`` (controlled
vocabularies, height required from 36 months) so a stored profile can always be turned
back into the context the chat and the tools accept. Age is never written: the profile
takes a date of birth and every age the API returns is derived from it in completed
months (hard rule 1; growth-tracking design Decision 1).
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import ActivityLevel, Allergen, DietPreference, NoteKind, Sex
from backend.nutrition.age import DATE_TOLERANCE, completed_months, today
from backend.schemas.tools import (
    _WEIGHT,
    HEIGHT_REQUIRED_FROM_MONTHS,
    MAX_AGE_MONTHS,
    MAX_HEIGHT_CM,
    MAX_NOTES,
    GrowthAssessmentResult,
    NoteRow,
    NutrientTargets,
    check_unique_notes,
)

AGE_OUT_OF_RANGE_DETAIL = (
    f"The supported range is newborn through {MAX_AGE_MONTHS} months; this child's date of "
    "birth puts them past it"
)
FUTURE_DATE_DETAIL = "cannot be later than today"


def not_after_today(value: dt.date, what: str) -> dt.date:
    """Reject a date past today (UTC) plus the one-day tolerance for parents east of UTC."""
    if value > today() + DATE_TOLERANCE:
        raise ValueError(f"{what} {FUTURE_DATE_DETAIL}")
    return value


def age_today(birth_date: dt.date) -> int:
    """Completed months today for a validated birth date; ``ValueError`` past 60 months.

    A birth date within the tolerance window ("tomorrow" east of UTC) counts as 0.
    """
    as_of = today()
    age = completed_months(birth_date, max(as_of, birth_date))
    if age > MAX_AGE_MONTHS:
        raise ValueError(AGE_OUT_OF_RANGE_DETAIL)
    return age


class ChildProfileWrite(BaseModel):
    """The whole profile, as the side-panel form submits it (create and replace)."""

    model_config = ConfigDict(extra="forbid")

    birth_date: dt.date = Field(description="Date of birth; age is derived in completed months.")
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    diet_preference: DietPreference = DietPreference.default()
    allergies: frozenset[Allergen] = Field(default_factory=frozenset)
    notes: list[NoteRow] = Field(default_factory=list, max_length=MAX_NOTES)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> ChildProfileWrite:
        age_months = age_today(not_after_today(self.birth_date, "birth_date"))
        if age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        check_unique_notes(self.notes)
        return self


class ChildNoteResponse(BaseModel):
    """One stored note row with its provenance (child-profile spec)."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    kind: NoteKind
    text: str
    recorded_at: dt.datetime


class ChildProfileResponse(BaseModel):
    """A stored profile. Allergies are returned sorted so responses compare stably."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    birth_date: dt.date
    age_months: int = Field(description="Completed months as of today, derived from birth_date.")
    weight_kg: float
    sex: Sex
    height_cm: float | None
    diet_preference: DietPreference
    allergies: list[Allergen]
    notes: list[ChildNoteResponse]
    activity_level: ActivityLevel
    created_at: dt.datetime


class DailyTargetsResponse(BaseModel):
    """The child's daily reference targets, for the side panel (child-profile spec).

    Deterministic: computed from the stored profile and the nutrient registry alone. The
    note rows are disclosed via ``doctor_notes_present`` and
    ``preferences_present``, never applied here -- it takes
    effect when meal plans are generated (day-9 design Decision 6).
    """

    model_config = ConfigDict(frozen=True)

    targets: NutrientTargets
    diet_preference: DietPreference
    doctor_notes_present: bool
    preferences_present: bool
    disclaimer: str


class GrowthMeasurementWrite(BaseModel):
    """One dated measurement as the Growth tab submits it (growth-tracking spec).

    Shape and "not in the future" are checked here; the rules that need the stored child
    (not before the birth date, not past 60 months, one per day) live in the route.
    """

    model_config = ConfigDict(extra="forbid")

    measured_on: dt.date
    weight_kg: float = _WEIGHT
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)

    @model_validator(mode="after")
    def _not_in_the_future(self) -> GrowthMeasurementWrite:
        not_after_today(self.measured_on, "measured_on")
        return self


class GrowthMeasurementResponse(BaseModel):
    """A stored measurement read back with what is derived from it on every read: the age
    on that day and the WHO assessment. ``assessment`` is ``None`` only when a later change
    to the birth date has put the measurement outside the 0-60-month standards."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    measured_on: dt.date
    age_months: int
    age_months_exact: float = Field(
        description=(
            "Age on the measurement day in months to two decimals, for placing the point on "
            "an age axis; the assessment uses completed months."
        )
    )
    weight_kg: float
    height_cm: float | None
    assessment: GrowthAssessmentResult | None
    created_at: dt.datetime
