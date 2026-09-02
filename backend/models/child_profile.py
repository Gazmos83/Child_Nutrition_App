"""Child nutrition profile models.

These carry the schema-level hard rules: age in months (rule 1), allergies and diet
preference as controlled vocabularies (rule 2), and the doctor's note whose guidance
overrides general nutrient targets (rule 3).
"""

import datetime as dt
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, Text
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from backend.models.enums import ActivityLevel, Allergen, DietPreference, Sex
from backend.nutrition.age import completed_months, today

if TYPE_CHECKING:
    from backend.models.feeding import Feeding
    from backend.models.growth_measurement import GrowthMeasurement
    from backend.models.user import User

# Newborn through ~4 years, the supported range. 60 months = 5 years exclusive upper
# bound on the product's scope.
MIN_AGE_MONTHS = 0
MAX_AGE_MONTHS = 60


class ChildProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A child's nutrition profile, owned by exactly one user."""

    __tablename__ = "child_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hard rule 1: age lives in months and only in months. The date of birth is the one
    # stored fact; the age is derived from it as completed months on demand (growth-tracking
    # design Decision 1), so it never goes stale. There is deliberately no `age_years`
    # column -- the failure mode "someone read age as years" cannot be expressed because
    # there is nothing to read (Day 1 design.md Decision 7).
    birth_date: Mapped[dt.date] = mapped_column(Date, nullable=False)

    # Fixed-point, not float: weight feeds per-kilogram nutrient arithmetic whose output
    # is a feeding instruction, so binary representation error has no place in the chain
    # (design.md Decision 6). Unit is kilograms, everywhere, with no alternative.
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    sex: Mapped[Sex] = mapped_column(pg_enum(Sex, "sex"), nullable=False)

    # Optional below 36 months, required from 36 (the DRI energy equation for 3-8 years
    # uses height); the request schema enforces that rule, the column only bounds it.
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)

    activity_level: Mapped[ActivityLevel] = mapped_column(
        pg_enum(ActivityLevel, "activity_level"),
        nullable=False,
        default=ActivityLevel.LOW_ACTIVE,
        server_default=ActivityLevel.LOW_ACTIVE.value,
    )

    diet_preference: Mapped[DietPreference] = mapped_column(
        pg_enum(DietPreference, "diet_preference"),
        nullable=False,
        default=DietPreference.default(),
        server_default=DietPreference.default().value,
    )

    # Clinician free text on purpose: this is professional input, not a system
    # vocabulary. Hard rule 2's no-free-text constraint governs allergies and diet
    # preference, not this field. Day 4 parses it into structured overrides; Day 1 only
    # guarantees it is captured with provenance (design.md Decision 9).
    doctors_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctors_note_recorded_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="child_profiles")

    allergies: Mapped[list[ChildAllergy]] = relationship(
        back_populates="child_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    feedings: Mapped[list[Feeding]] = relationship(
        back_populates="child_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    growth_measurements: Mapped[list[GrowthMeasurement]] = relationship(
        back_populates="child_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    #: Read/write view of :attr:`allergies` as plain :class:`Allergen` values.
    allergens: AssociationProxy[list[Allergen]] = association_proxy(
        "allergies",
        "allergen",
        creator=lambda allergen: ChildAllergy(allergen=allergen),
    )

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_kg_positive"),
        CheckConstraint("height_cm IS NULL OR height_cm > 0", name="height_cm_positive"),
        # Either a note with its timestamp, or neither. Keeps "a note nobody can date"
        # out of the database (design.md Decision 9).
        CheckConstraint(
            "(doctors_note IS NULL) = (doctors_note_recorded_at IS NULL)",
            name="doctors_note_paired_with_timestamp",
        ),
    )

    def age_months_on(self, as_of: dt.date) -> int:
        """Completed months of age on ``as_of`` (hard rule 1)."""
        return completed_months(self.birth_date, as_of)

    @property
    def age_months(self) -> int:
        """Completed months of age today (UTC). Clamped at 0 for a child born "tomorrow"
        in the parent's time zone (growth-tracking design Decision 2)."""
        if self.birth_date > today():
            return MIN_AGE_MONTHS
        return self.age_months_on(today())

    def __repr__(self) -> str:
        return (
            f"<ChildProfile id={self.id} birth_date={self.birth_date} weight_kg={self.weight_kg}>"
        )


class ChildAllergy(Base):
    """A single allergen recorded against a child profile.

    The composite primary key *is* the deduplication guarantee -- recording the same
    allergen twice violates the primary key rather than relying on application logic
    that a future code path could bypass (design.md Decision 8).

    "No allergies" is the empty set of these rows; there is no sentinel member.
    """

    __tablename__ = "child_allergies"

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    allergen: Mapped[Allergen] = mapped_column(
        pg_enum(Allergen, "allergen"),
        primary_key=True,
    )

    child_profile: Mapped[ChildProfile] = relationship(back_populates="allergies")

    # No UniqueConstraint here on purpose: the composite primary key above already
    # enforces uniqueness on exactly these columns, and adding one would create a second
    # index covering the same tuple for no benefit.

    def __repr__(self) -> str:
        return f"<ChildAllergy child_profile_id={self.child_profile_id} allergen={self.allergen}>"
