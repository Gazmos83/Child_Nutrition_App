"""SQLAlchemy ORM models and controlled vocabularies.

Every model is imported here so that ``Base.metadata`` is fully populated by importing
this package alone -- Alembic autogenerate and the test schema fixtures both rely on it.
"""

from backend.db.base import Base
from backend.models.child_note import ChildNote
from backend.models.child_profile import ChildAllergy, ChildProfile
from backend.models.enums import (
    ActivityLevel,
    Allergen,
    DietPreference,
    FeedingType,
    NoteKind,
    Sex,
)
from backend.models.feeding import Feeding
from backend.models.food_table_revision import FoodTableRevision
from backend.models.growth_measurement import GrowthMeasurement
from backend.models.user import User

__all__ = [
    "ActivityLevel",
    "Allergen",
    "Base",
    "ChildAllergy",
    "ChildNote",
    "ChildProfile",
    "DietPreference",
    "Feeding",
    "FeedingType",
    "FoodTableRevision",
    "GrowthMeasurement",
    "NoteKind",
    "Sex",
    "User",
]
