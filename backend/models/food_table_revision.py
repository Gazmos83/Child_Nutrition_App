"""Whole-table revisions of the food-composition table (food-table-admin design Decision 1).

One row per administrative write, each holding the complete validated table as JSONB. A
plan's ``food_table_version`` (``db-<revision>``) names one of these rows, so the table a
recommendation was composed from can be reproduced exactly (hard rule 8). Revision 1 is
seeded from ``nutrition-data/foods.yaml`` by the migration.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin


class FoodTableRevision(TimestampMixin, Base):
    __tablename__ = "food_table_revisions"

    # Assigned as latest + 1 by the writer, not by a sequence: two writers racing for the
    # same next revision collide on the primary key and the loser is told to reload.
    revision: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    table: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)

    def __repr__(self) -> str:
        return f"<FoodTableRevision revision={self.revision} summary={self.summary!r}>"
