"""SQLAlchemy ORM models and controlled vocabularies.

Every model is imported here so that ``Base.metadata`` is fully populated by importing
this package alone -- Alembic autogenerate and the test schema fixtures both rely on it.
"""

from backend.db.base import Base
from backend.models.child_profile import ChildAllergy, ChildProfile
from backend.models.enums import Allergen, DietPreference, Sex
from backend.models.user import User

__all__ = [
    "Allergen",
    "Base",
    "ChildAllergy",
    "ChildProfile",
    "DietPreference",
    "Sex",
    "User",
]
