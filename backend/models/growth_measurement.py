"""The persisted growth log (growth-tracking spec).

Each row is one dated measurement of a child's weight and, when taken, length/height --
stored raw. The age on that day and the WHO assessment are derived on every read
(``backend/api/children.py``), never stored, the same stance the feeding log takes on
nutrients. ``GrowthMeasurementWrite`` in ``backend/schemas/child.py`` is the validation
boundary for every write; the constraints here are the database's own copy.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.child_profile import ChildProfile


class GrowthMeasurement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One dated weight/length measurement, owned through its child profile (hard rule 9)."""

    __tablename__ = "growth_measurements"

    # No separate index: the unique constraint below leads on this column and doubles as
    # the list's ordering index (growth-tracking design Decision 4).
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profiles.id", ondelete="CASCADE"), nullable=False
    )

    # A calendar day, not a timestamp: growth is measured once, and a time of day would be
    # invented. One measurement per child per day defines "newest" without a tie-break.
    measured_on: Mapped[dt.date] = mapped_column(Date, nullable=False)

    # Fixed-point like the profile's own columns (Day 1 design.md Decision 6).
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)

    child_profile: Mapped[ChildProfile] = relationship(back_populates="growth_measurements")

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_kg_positive"),
        CheckConstraint("height_cm IS NULL OR height_cm > 0", name="height_cm_positive"),
        # Named explicitly: the `uq_` convention would name it after the first column only.
        UniqueConstraint(
            "child_profile_id", "measured_on", name="uq_growth_measurements_child_day"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<GrowthMeasurement id={self.id} measured_on={self.measured_on} "
            f"weight_kg={self.weight_kg}>"
        )
