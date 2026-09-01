"""The curated food-composition table (design.md Decision 2; food-composition-data spec).

``nutrition-data/foods.yaml`` is validated whole at load time: one invalid entry fails the
load with an error naming it, and no partial table is ever handed to callers. A food
missing its safety flags would otherwise be *admitted* to infant plans.
"""

import difflib
import logging
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.models.enums import Allergen
from backend.schemas.tools import MAX_AGE_MONTHS, MIN_AGE_MONTHS

logger = logging.getLogger(__name__)

DEFAULT_FOOD_TABLE_PATH = Path("nutrition-data") / "foods.yaml"


class FoodCategory(StrEnum):
    """Food groups, used for diet-preference exclusions and plan variety.

    Not a database enum: it describes rows in a committed YAML file, not user data.
    """

    MILK_FEED = "milk_feed"  # breast milk, infant formula
    DAIRY = "dairy"
    EGG = "egg"
    MEAT = "meat"
    POULTRY = "poultry"
    FISH = "fish"
    SHELLFISH = "shellfish"
    LEGUME = "legume"
    GRAIN = "grain"
    VEGETABLE = "vegetable"
    FRUIT = "fruit"
    NUT_SEED = "nut_seed"
    FAT_OIL = "fat_oil"
    SWEETENER = "sweetener"


class FoodItem(BaseModel):
    """One food: per-serving nutrients, safety metadata, and provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    category: FoodCategory
    serving_size: float = Field(gt=0)
    serving_unit: str = Field(min_length=1)

    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    iron_mg: float = Field(ge=0)
    calcium_mg: float = Field(ge=0)

    allergens: frozenset[Allergen] = Field(default_factory=frozenset)
    choking_hazard: bool
    contains_honey: bool
    commonly_unpasteurized: bool
    min_age_months: int = Field(ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)

    source: str | None = Field(
        default=None, description="Overrides the table-level source for this entry."
    )
    notes: str | None = None


class FoodTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Default provenance for every entry.")
    foods: list[FoodItem] = Field(min_length=1)

    def by_id(self) -> dict[str, FoodItem]:
        return {food.id: food for food in self.foods}

    def source_for(self, food: FoodItem) -> str:
        return food.source or self.source


class FoodNotFoundError(LookupError):
    """The string as given, plus ``"id (Name)"`` candidates the caller may surface.

    The message prefix is load-bearing: the chat layer classifies tool failures by
    ``startswith("Unknown food")``.
    """

    def __init__(self, food_id: str, suggestions: tuple[str, ...] = ()) -> None:
        message = f"Unknown food id {food_id!r}"
        if suggestions:
            message += ". Closest matches: " + ", ".join(suggestions)
        super().__init__(message)
        self.food_id = food_id
        self.suggestions = suggestions


# Filler words in display names ("Sweet potato, cooked and mashed") that carry no food
# identity. Preparation words (cooked, mashed, raw, whole) are deliberately NOT here:
# they separate e.g. carrot_cooked_mashed from raw_carrot_sticks.
_STOPWORDS = frozenset("a and as from in its made of or the to until with".split())

_MAX_SUGGESTIONS = 5


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _variants(token: str) -> frozenset[str]:
    """The token plus naive singular forms, applied to both sides so plurals meet."""
    forms = {token}
    if token.endswith("es"):
        forms.add(token[:-2])
    if token.endswith("s"):
        forms.add(token[:-1])
    return frozenset(forms)


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(
        variant
        for token in _normalize(text).split()
        if token not in _STOPWORDS
        for variant in _variants(token)
    )


class LoadedFoodTable:
    """A validated table with id lookup. Immutable after construction."""

    def __init__(self, table: FoodTable) -> None:
        self.table = table
        self._by_id = table.by_id()
        # Resolution index: each food's normalized id/name forms and its token pool
        # (id and name tokens with plural variants), built once -- the table is frozen.
        self._forms: dict[str, FoodItem] = {}
        self._token_pools: list[tuple[FoodItem, frozenset[str]]] = []
        for food in table.foods:
            for form in (_normalize(food.id), _normalize(food.name)):
                self._forms.setdefault(form, food)
            self._token_pools.append((food, _tokenize(f"{food.id} {food.name}")))

    @property
    def version(self) -> str:
        return self.table.version

    @property
    def foods(self) -> list[FoodItem]:
        return list(self.table.foods)

    def get(self, food_id: str) -> FoodItem:
        """Return the food or raise ``FoodNotFoundError`` -- never a default or a lookalike."""
        try:
            return self._by_id[food_id]
        except KeyError:
            raise FoodNotFoundError(food_id) from None

    def resolve(self, query: str) -> FoodItem:
        """Resolve an exact id or a plain-language name to exactly one food.

        Deterministic and code-only: exact id, then normalized id/name equality, then a
        token-subset match that must single out one food. Anything ambiguous or unknown
        raises ``FoodNotFoundError`` carrying ``"id (Name)"`` suggestions -- never a
        lookalike (food-composition-data spec).
        """
        if query in self._by_id:
            return self._by_id[query]

        normalized = _normalize(query)
        exact = self._forms.get(normalized)
        if exact is not None:
            return exact

        query_tokens = [
            _variants(token) for token in normalized.split() if token not in _STOPWORDS
        ]
        if query_tokens:
            contained = [
                food
                for food, pool in self._token_pools
                if all(variants & pool for variants in query_tokens)
            ]
            if len(contained) == 1:
                return contained[0]
            if contained:
                raise FoodNotFoundError(query, _suggestions(contained))

        return self._raise_with_close_matches(query, normalized)

    def _raise_with_close_matches(self, query: str, normalized: str) -> FoodItem:
        close = difflib.get_close_matches(normalized, self._forms, n=_MAX_SUGGESTIONS)
        candidates: list[FoodItem] = []
        for form in close:
            food = self._forms[form]
            if food not in candidates:
                candidates.append(food)
        raise FoodNotFoundError(query, _suggestions(candidates))

    def source_for(self, food: FoodItem) -> str:
        return self.table.source_for(food)

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, food_id: object) -> bool:
        return food_id in self._by_id


def _suggestions(foods: list[FoodItem]) -> tuple[str, ...]:
    return tuple(f"{food.id} ({food.name})" for food in foods[:_MAX_SUGGESTIONS])


def load_food_table(path: str | Path = DEFAULT_FOOD_TABLE_PATH) -> LoadedFoodTable:
    """Read and validate the whole table, or raise ``ValueError`` naming the problem."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Food table not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid {path}: {exc}") from exc
    try:
        table = FoodTable.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid {path}: {_describe(exc, raw)}") from exc

    seen: set[str] = set()
    for food in table.foods:
        if food.id in seen:
            raise ValueError(f"Invalid {path}: food id {food.id!r} is listed twice")
        seen.add(food.id)

    logger.info("Loaded food table %s: %d foods (version %s)", path, len(seen), table.version)
    return LoadedFoodTable(table)


def _describe(exc: ValidationError, raw: object) -> str:
    """Name the offending entry (by id when it has one) for each validation error."""
    lines: list[str] = []
    foods = raw.get("foods") if isinstance(raw, dict) else None
    for error in exc.errors():
        loc = error["loc"]
        where = ".".join(str(part) for part in loc)
        if len(loc) >= 2 and loc[0] == "foods" and isinstance(loc[1], int):
            entry = foods[loc[1]] if isinstance(foods, list) and loc[1] < len(foods) else None
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            where = f"foods[{loc[1]}]" + (f" ({entry_id})" if entry_id else "")
            if len(loc) > 2:
                where += "." + ".".join(str(part) for part in loc[2:])
        lines.append(f"{where}: {error['msg']}")
    return "; ".join(lines)


@lru_cache(maxsize=1)
def get_food_table() -> LoadedFoodTable:
    """Process-wide table, loaded on first use from the committed file."""
    return load_food_table(DEFAULT_FOOD_TABLE_PATH)


def reset_food_table_cache() -> None:
    """For tests that swap the table."""
    get_food_table.cache_clear()
