"""SQLAlchemy declarative base and shared column mixins."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names. Without this, PostgreSQL invents names for CHECK and
# UNIQUE constraints, and a later migration that needs to drop one has nothing stable to
# reference -- Alembic autogenerate emits `None` for the constraint name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Design Decision 10: every timestamp is TIMESTAMPTZ. Mapping the annotation here
    # rather than per-column means a bare `Mapped[datetime]` cannot silently produce a
    # naive TIMESTAMP column -- an ambiguous time in a health record is a defect.
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


def pg_enum(enum_class: type[StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum type from a ``StrEnum``.

    ``values_callable`` is not optional. By default SQLAlchemy persists enum *names*
    (``MALE``), not values (``male``), which would put uppercase labels in the database
    while the Python vocabulary reads lowercase. Passing the values explicitly keeps the
    two in step -- see design.md Decision 2.
    """
    return Enum(
        enum_class,
        name=name,
        native_enum=True,
        create_type=True,
        values_callable=lambda enum: [member.value for member in enum],
    )


class UUIDPrimaryKeyMixin:
    """A UUIDv7 primary key.

    UUIDv7 (stdlib in Python 3.14) is time-ordered in its high bits, so it retains the
    index locality of a sequential key while its random tail defeats enumeration. The
    ``user-account`` spec requires identifiers that cannot be derived by incrementing --
    a sequential integer in a URL would be an enumeration vector against a children's
    health record. See design.md Decision 3.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid7,
    )


class TimestampMixin:
    """A server-generated creation timestamp.

    ``TIMESTAMPTZ`` rather than a naive timestamp: an ambiguous time in a health record
    is a defect. The default is applied by the database so that migrations and manual
    fixes get the same value the application would (design.md Decision 10).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
