"""Administrative edits to the food table, as pure functions over ``FoodTable``
(food-table-admin design Decisions 1, 4 and 6).

Every path here produces a whole candidate table and validates it exactly as the committed
file is validated, so an administrator can never write a table the loader would refuse.
Persistence (``backend/db/food_table.py``) and HTTP (``backend/api/admin_foods.py``) sit
around this module; nothing here touches a database, a request, or a model.
"""

import csv
import io
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.nutrition.foods import (
    FoodCategory,
    FoodItem,
    FoodNotFoundError,
    FoodTable,
    _check_unique_ids,
    _describe,
)

# Hard-wired by the feeding log's milk-feed defaults and the planner's milk anchor: these two
# cannot be deactivated or moved out of ``milk_feed``, and no other food may join them.
PROTECTED_FOOD_IDS = frozenset({"breast_milk", "infant_formula_iron_fortified"})
IMPORT_MAX_BYTES = 1_048_576
PENDING_VERSION = "pending"

_BOOL_FIELDS = ("choking_hazard", "contains_honey", "commonly_unpasteurized", "is_active")
_NUMBER_FIELDS = (
    "serving_size",
    "calories",
    "protein_g",
    "fat_g",
    "carbohydrate_g",
    "iron_mg",
    "calcium_mg",
)


class FoodWrite(FoodItem):
    """An administrator's entry: the table's own shape with the source made mandatory
    (hard rule 5 -- a number never enters the table without its provenance)."""

    source: str = Field(min_length=1, description="Where these values come from.")


class AdminRuleError(ValueError):
    """A write that the table shape allows but the administration rules do not."""

    def __init__(self, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


class DuplicateFoodError(AdminRuleError):
    def __init__(self, food_id: str) -> None:
        super().__init__(f"A food with id {food_id!r} already exists", conflict=True)


def snapshot(table: FoodTable) -> dict:
    """The table as a database revision stores it: source and foods, no version."""
    return {"source": table.source, "foods": [f.model_dump(mode="json") for f in table.foods]}


def validate_table(payload: dict) -> FoodTable:
    """Validate a candidate ``{source, foods}`` whole; ``ValueError`` names the entry."""
    raw = {**payload, "version": PENDING_VERSION}
    try:
        table = FoodTable.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(_describe(exc, raw)) from exc
    _check_unique_ids(table)
    return table


def check_admin_rules(food: FoodItem) -> None:
    """The protected milk feeds keep their category; nothing else may claim it."""
    if food.category is FoodCategory.MILK_FEED and food.id not in PROTECTED_FOOD_IDS:
        raise AdminRuleError(
            "the milk_feed category is reserved for breast milk and iron-fortified formula"
        )
    if food.id in PROTECTED_FOOD_IDS and food.category is not FoodCategory.MILK_FEED:
        raise AdminRuleError(f"{food.id} must stay a milk feed", conflict=True)


def _with_entry(current: FoodTable, food: FoodItem) -> FoodTable:
    foods = [food if existing.id == food.id else existing for existing in current.foods]
    if all(existing.id != food.id for existing in current.foods):
        foods.append(food)
    return validate_table(
        {"source": current.source, "foods": [f.model_dump(mode="json") for f in foods]}
    )


def apply_write(current: FoodTable, food: FoodItem, *, create: bool) -> FoodTable:
    """The table with ``food`` created (id must be new) or replaced (id must exist)."""
    check_admin_rules(food)
    exists = food.id in current.by_id()
    if create and exists:
        raise DuplicateFoodError(food.id)
    if not create and not exists:
        raise FoodNotFoundError(food.id)
    return _with_entry(current, food)


def set_active(current: FoodTable, food_id: str, active: bool) -> tuple[FoodTable, bool]:
    """The table with the food's active flag set; ``changed`` is False when it already was."""
    existing = current.by_id().get(food_id)
    if existing is None:
        raise FoodNotFoundError(food_id)
    if not active and food_id in PROTECTED_FOOD_IDS:
        raise AdminRuleError(f"{food_id} cannot be deactivated", conflict=True)
    if existing.is_active == active:
        return current, False
    return _with_entry(current, existing.model_copy(update={"is_active": active})), True


# -- bulk import ----------------------------------------------------------------------------


class ImportRowError(BaseModel):
    model_config = ConfigDict(frozen=True)

    row: int = Field(ge=0, description="1-based row in the file; 0 for a whole-file problem.")
    id: str | None = None
    field: str | None = None
    message: str


@dataclass
class ImportPlan:
    """What an import would do; ``table`` is None when any row failed."""

    table: FoodTable | None
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)

    @property
    def changes_anything(self) -> bool:
        return bool(self.created or self.updated)


def parse_import(format: str, content: str) -> tuple[list[dict], str | None]:
    """Rows as plain dicts plus the file-level source, or ``ValueError`` for an unreadable file.

    YAML: a bare list of entries or ``{source?, foods: [...]}`` like the committed file.
    CSV: a header of field names; ``allergens`` ``;``-separated; booleans ``true``/``false``;
    blank optional cells become null.
    """
    if len(content.encode("utf-8")) > IMPORT_MAX_BYTES:
        raise ValueError(f"the file is larger than {IMPORT_MAX_BYTES // 1024} KiB")
    if format == "yaml":
        try:
            raw = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValueError(f"the file is not valid YAML: {exc}") from exc
        if isinstance(raw, list):
            return [r for r in raw], None
        if isinstance(raw, dict) and isinstance(raw.get("foods"), list):
            source = raw.get("source")
            return list(raw["foods"]), source if isinstance(source, str) else None
        raise ValueError("the file must be a list of foods or a mapping with a 'foods' list")
    if format == "csv":
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ValueError("the file has no header row")
        return [_csv_row(row) for row in reader], None
    raise ValueError(f"unknown import format {format!r}")


def _csv_row(row: dict) -> dict:
    out: dict = {}
    for key, value in row.items():
        if key is None:
            continue
        key = key.strip()
        text = (value or "").strip() if isinstance(value, str) else value
        if text in ("", None):
            if key in ("source", "notes"):
                out[key] = None
            continue
        if key == "allergens":
            out[key] = [part.strip() for part in text.split(";") if part.strip()]
        elif key in _BOOL_FIELDS:
            out[key] = _bool(text)
        elif key in _NUMBER_FIELDS or key == "min_age_months":
            out[key] = _number(text)
        else:
            out[key] = text
    return out


def _bool(text: str) -> object:
    lowered = text.lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    return text  # let validation name the field


def _number(text: str) -> object:
    try:
        return int(text) if text.isdigit() else float(text)
    except ValueError:
        return text


def _effective(current: FoodTable, food: FoodItem) -> dict:
    """An entry as it reads with the table's default source filled in, for change detection."""
    return {**food.model_dump(mode="json"), "source": current.source_for(food)}


def plan_import(
    current: FoodTable, rows: list[dict], mode: str, file_source: str | None
) -> ImportPlan:
    """Merge ``rows`` into ``current`` and validate the result whole; never partial."""
    plan = ImportPlan(table=None)
    existing = current.by_id()
    merged: dict[str, FoodItem] = {}
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            plan.errors.append(ImportRowError(row=index, message="a row must be a mapping"))
            continue
        row = dict(raw)
        if not row.get("source") and file_source:
            row["source"] = file_source
        food_id = row.get("id") if isinstance(row.get("id"), str) else None
        try:
            food = FoodWrite.model_validate(row)
            check_admin_rules(food)
        except ValidationError as exc:
            first = exc.errors()[0]
            field_name = ".".join(str(p) for p in first["loc"]) or None
            plan.errors.append(
                ImportRowError(row=index, id=food_id, field=field_name, message=first["msg"])
            )
            continue
        except AdminRuleError as exc:
            plan.errors.append(ImportRowError(row=index, id=food_id, message=str(exc)))
            continue
        if food.id in seen:
            plan.errors.append(
                ImportRowError(
                    row=index, id=food.id, field="id", message="listed twice in the file"
                )
            )
            continue
        seen.add(food.id)
        before = existing.get(food.id)
        if before is None:
            plan.created.append(food.id)
        elif mode == "create_only":
            plan.errors.append(
                ImportRowError(row=index, id=food.id, field="id", message="already exists")
            )
            continue
        elif _effective(current, before) == _effective(current, food):
            plan.unchanged.append(food.id)
        else:
            plan.updated.append(food.id)
        merged[food.id] = food
    if plan.errors:
        plan.created, plan.updated, plan.unchanged = [], [], []
        return plan
    foods = [merged.get(f.id, f) for f in current.foods] + [merged[fid] for fid in plan.created]
    try:
        plan.table = validate_table(
            {"source": current.source, "foods": [f.model_dump(mode="json") for f in foods]}
        )
    except ValueError as exc:
        plan.errors.append(ImportRowError(row=0, message=str(exc)))
        plan.created, plan.updated, plan.unchanged = [], [], []
    return plan
