"""Request and response models for ``/api/admin/foods`` (food-table-admin spec)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.nutrition.food_admin import IMPORT_MAX_BYTES, ImportRowError
from backend.nutrition.foods import FoodItem


class FoodTableAdminResponse(BaseModel):
    """Every entry, inactive included, with the served version and revision."""

    model_config = ConfigDict(frozen=True)

    version: str
    revision: int
    source: str
    foods: list[FoodItem]


class FoodWriteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    food: FoodItem
    version: str
    revision: int


class FoodImportRequest(BaseModel):
    """A file's text, sent as JSON: the API keeps its JSON-only CSRF posture and needs no
    multipart parser (design Decision 6)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["yaml", "csv"]
    content: str = Field(min_length=1, max_length=IMPORT_MAX_BYTES)
    mode: Literal["upsert", "create_only"] = "upsert"
    dry_run: bool = False


class FoodImportResult(BaseModel):
    """What the import did, or would do. ``applied`` is true only when a revision was written."""

    model_config = ConfigDict(frozen=True)

    applied: bool
    created: list[str]
    updated: list[str]
    unchanged: list[str]
    errors: list[ImportRowError]
    version: str
    revision: int
