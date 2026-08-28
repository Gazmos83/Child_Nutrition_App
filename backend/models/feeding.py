"""The persisted feeding log (reference §9b; feeding-log spec).

Each row records what a child was *actually* fed, distinct from any planned meal. The
shape rules mirror :class:`backend.schemas.tools.FeedingEntry`, which stays the validation
boundary for every write; the constraints here are the database's own copy of the rules
that keep a stored row convertible to table nutrients.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from backend.models.enums import FeedingType

if TYPE_CHECKING:
    from backend.models.child_profile import ChildProfile

# Mirrors FeedingUnit in backend/schemas/tools.py. Kept as a CHECK rather than a fourth
# enum type: two labels that will not grow do not earn a migration-per-change type.
FEEDING_UNITS = ("ml", "g")
FOOD_ID_MAX_LENGTH = 64


class Feeding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One logged feed, owned through its child profile (hard rule 9)."""

    __tablename__ = "feedings"

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When the feed happened, as the parent reported it. TIMESTAMPTZ via the base
    # annotation map (design.md Decision 10); the local day is derived at read time from
    # the parent's time zone, never stored.
    fed_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    feeding_type: Mapped[FeedingType] = mapped_column(
        pg_enum(FeedingType, "feeding_type"), nullable=False
    )

    # A food-table id (nutrition-data/foods.yaml), not a foreign key: the table is a
    # versioned YAML file, not a database relation. Required for solids, optional for
    # milk feeds, never present for water -- enforced by FeedingEntry on write.
    food_id: Mapped[str | None] = mapped_column(String(FOOD_ID_MAX_LENGTH), nullable=True)

    # Nullable only for breast milk (no measure exists); fixed-point like weight_kg.
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(2), nullable=False, server_default="ml")

    child_profile: Mapped[ChildProfile] = relationship(back_populates="feedings")

    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "quantity IS NOT NULL OR feeding_type = 'breastmilk'",
            name="quantity_required_unless_breastmilk",
        ),
        CheckConstraint("unit IN ('ml', 'g')", name="unit_known"),
    )

    def __repr__(self) -> str:
        return f"<Feeding id={self.id} type={self.feeding_type} fed_at={self.fed_at}>"
