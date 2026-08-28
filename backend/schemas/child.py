"""Request and response models for ``/api/children`` (child-profile spec).

The write model shares its field definitions with ``ChildContext`` (ages in months,
controlled vocabularies, height required from 36 months) so a stored profile can always
be turned back into the context the chat and the tools accept.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import ActivityLevel, Allergen, DietPreference, Sex
from backend.schemas.tools import (
    _AGE,
    _WEIGHT,
    HEIGHT_REQUIRED_FROM_MONTHS,
    MAX_HEIGHT_CM,
)

MAX_DOCTORS_NOTE_CHARS = 4000


class ChildProfileWrite(BaseModel):
    """The whole profile, as the side-panel form submits it (create and replace)."""

    model_config = ConfigDict(extra="forbid")

    age_months: int = _AGE
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    diet_preference: DietPreference = DietPreference.default()
    allergies: frozenset[Allergen] = Field(default_factory=frozenset)
    doctors_note: str | None = Field(default=None, max_length=MAX_DOCTORS_NOTE_CHARS)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> ChildProfileWrite:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        if self.doctors_note is not None and not self.doctors_note.strip():
            self.doctors_note = None
        return self


class ChildProfileResponse(BaseModel):
    """A stored profile. Allergies are returned sorted so responses compare stably."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    age_months: int
    weight_kg: float
    sex: Sex
    height_cm: float | None
    diet_preference: DietPreference
    allergies: list[Allergen]
    doctors_note: str | None
    doctors_note_recorded_at: dt.datetime | None
    activity_level: ActivityLevel
    created_at: dt.datetime
