"""Doctor's-note and preference rows (child-notes-restrictions; child-profile spec).

One row per instruction, tagged with who it came from. The text is clinician or parent free
text on purpose (hard rule 2 governs allergies, diet preference, and the row's ``kind``, not
this field); the day-4 extraction turns rows into bounded structures before anything acts on
them. Length (500) and the row cap (20) are Pydantic rules so a backfilled longer note is
kept intact.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from backend.models.enums import NoteKind

if TYPE_CHECKING:
    from backend.models.child_profile import ChildProfile


class ChildNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One note row, owned through its child profile (hard rule 9)."""

    __tablename__ = "child_notes"

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[NoteKind] = mapped_column(pg_enum(NoteKind, "note_kind"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Display order within the profile; not unique because a whole-profile replace reorders
    # rows in one unit of work (design Decision 1).
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    child_profile: Mapped[ChildProfile] = relationship(back_populates="notes")

    __table_args__ = (
        CheckConstraint("btrim(text) <> ''", name="text_not_blank"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<ChildNote id={self.id} kind={self.kind} position={self.position}>"
