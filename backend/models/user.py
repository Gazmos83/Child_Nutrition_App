"""The user account model -- the authorization anchor for all user-scoped data."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.child_profile import ChildProfile

# RFC 5321 caps a forward path at 256 octets; 320 is the conventional generous ceiling
# (64 local part + @ + 255 domain).
EMAIL_MAX_LENGTH = 320


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered user who owns child profiles.

    Every user-scoped record hangs off this table's primary key. Day 6 attaches
    credential verification; Day 1 lands the columns and the ownership edges only, and
    deliberately exposes no route that reads user-scoped data (design.md Risk 6).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), nullable=False)

    # Written first on Day 6. The algorithm (argon2 vs bcrypt) is a Day 6 decision, so no
    # hashing library is a Day 1 dependency. NOT NULL rather than nullable: a nullable
    # password column would encode an invariant the database cannot enforce
    # ("a password or an external subject, never neither") -- design.md Decision 5.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    child_profiles: Mapped[list[ChildProfile]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Case-insensitive uniqueness via a functional index rather than a citext column:
        # citext is an extension some managed providers restrict, and lower-casing on
        # write would destroy the user's original casing (design.md Decision 4).
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
