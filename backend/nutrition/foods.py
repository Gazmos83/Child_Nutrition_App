"""The curated food-composition table (design.md Decision 2; food-composition-data spec).

The table is validated whole: one invalid entry fails the load with an error naming it, and
no partial table is ever handed to callers. A food missing its safety flags would otherwise
be *admitted* to infant plans. Since food-table-admin the served table comes from the
database's latest whole-table revision (``set_food_table``); ``nutrition-data/foods.yaml``
seeds that database and is the fallback whenever no database table has been loaded.
"""

import difflib
import logging
import re
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    model_validator,
)

from backend.models.enums import Allergen
from backend.schemas.tools import MAX_AGE_MONTHS, MIN_AGE_MONTHS

logger = logging.getLogger(__name__)

DEFAULT_FOOD_TABLE_PATH = Path("nutrition-data") / "foods.yaml"

# WHO/AAP: complementary foods from about 6 months; only milk feeds are for younger infants.
SOLIDS_MIN_AGE_MONTHS = 6


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

    # Optional micronutrients (food-micronutrients): ``None`` means "not measured" and is
    # deliberately distinct from a measured zero -- a default of 0.0 would be a nutrition
    # claim with no source (hard rule 5). Optional also keeps every stored table revision
    # re-validating as-is, so there is no migration. Units follow the registry convention
    # (mg -> _mg, g -> _g, µg -> _ug).
    zinc_mg: float | None = Field(default=None, ge=0)
    vitamin_a_ug: float | None = Field(default=None, ge=0)
    iodine_ug: float | None = Field(default=None, ge=0)
    vitamin_b12_ug: float | None = Field(default=None, ge=0)
    folate_ug: float | None = Field(default=None, ge=0)
    vitamin_c_mg: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)

    allergens: frozenset[Allergen] = Field(default_factory=frozenset)
    choking_hazard: bool
    contains_honey: bool
    commonly_unpasteurized: bool
    min_age_months: int = Field(ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)

    source: str | None = Field(
        default=None, description="Overrides the table-level source for this entry."
    )
    notes: str | None = None
    # food-table-admin: a withdrawn food leaves the picker, the planner, and name lookup but
    # stays retrievable by id so feeds already logged with it still price. Not a safety
    # flag, so a default is acceptable.
    is_active: bool = True

    @model_validator(mode="after")
    def _age_matches_category(self) -> FoodItem:
        if self.category is FoodCategory.MILK_FEED:
            if self.min_age_months != MIN_AGE_MONTHS:
                raise ValueError("a milk feed's min_age_months must be 0")
        elif self.min_age_months < SOLIDS_MIN_AGE_MONTHS:
            raise ValueError(
                f"a solid food's min_age_months must be at least {SOLIDS_MIN_AGE_MONTHS}"
            )
        return self

    @field_serializer("allergens")
    def _sorted_allergens(self, value: frozenset[Allergen]) -> list[str]:
        """Sorted, so snapshots and seeds serialise deterministically."""
        return sorted(a.value for a in value)


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
_STOPWORDS = frozenset(
    ["a", "and", "as", "from", "in", "its", "made", "of", "or", "the", "to", "until", "with"]
)

_MAX_SUGGESTIONS = 5

# Query-side noise (food-lookup-quantities design Decision 4): words that describe an
# amount or frame a question, never a food. Dropped from the *query* only -- the index is
# untouched -- and never used to choose between foods. Preparation words (cooked, mashed,
# raw, whole) and nutrient names (iron, calcium appear in food names) stay out on purpose;
# ``tests/test_tools_nutrient.py`` asserts this set is disjoint from every table pool.
_QUERY_NOISE = frozenset(
    {
        # units
        "g",
        "gram",
        "grams",
        "ml",
        "millilitre",
        "millilitres",
        "milliliter",
        "milliliters",
        "oz",
        "ounce",
        "ounces",
        "cup",
        "cups",
        "tbsp",
        "tablespoon",
        "tablespoons",
        "tsp",
        "teaspoon",
        "teaspoons",
        # measure words
        "piece",
        "pieces",
        "serving",
        "servings",
        "portion",
        "portions",
        "half",
        "quarter",
        "some",
        "about",
        "roughly",
        "approximately",
        "around",
        "per",
        "for",
        # question and framing words
        "what",
        "how",
        "many",
        "much",
        "is",
        "are",
        "does",
        "do",
        "have",
        "has",
        "there",
        "nutritional",
        "nutrition",
        "nutrient",
        "nutrients",
        "value",
        "values",
        "calories",
        "kcal",
        "macros",
    }
)


def _is_noise(token: str) -> bool:
    return token[0].isdigit() or token in _QUERY_NOISE


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
    """A validated table with id lookup. Immutable after construction.

    ``foods``, name resolution, ``len`` and ``in`` see active entries only -- what the
    picker, the planner, and the chat tools may offer. ``get`` and ``all_foods`` see every
    entry, so a stored feed can always be priced (food-table-admin design Decision 3).
    """

    def __init__(self, table: FoodTable) -> None:
        self.table = table
        self._all_by_id = table.by_id()
        self._active = [food for food in table.foods if food.is_active]
        self._by_id = {food.id: food for food in self._active}
        # Resolution index over active entries: each food's normalized id/name forms and
        # its token pool (id and name tokens with plural variants), built once.
        self._forms: dict[str, FoodItem] = {}
        self._token_pools: list[tuple[FoodItem, frozenset[str]]] = []
        for food in self._active:
            for form in (_normalize(food.id), _normalize(food.name)):
                self._forms.setdefault(form, food)
            self._token_pools.append((food, _tokenize(f"{food.id} {food.name}")))

    @property
    def version(self) -> str:
        return self.table.version

    @property
    def foods(self) -> list[FoodItem]:
        """Active entries only."""
        return list(self._active)

    @property
    def all_foods(self) -> list[FoodItem]:
        """Every entry, inactive included (the administrator's view)."""
        return list(self.table.foods)

    def get(self, food_id: str) -> FoodItem:
        """Return the food -- inactive included -- or raise ``FoodNotFoundError``; never a
        default or a lookalike."""
        try:
            return self._all_by_id[food_id]
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

        # Amount and question words around the food are ignored; if nothing else is
        # left ("20 grams"), the original words stand so the refusal names what was said.
        words = [token for token in normalized.split() if token not in _STOPWORDS]
        core = [token for token in words if not _is_noise(token)] or words
        if core != words:
            normalized = " ".join(core)
            exact = self._forms.get(normalized)
            if exact is not None:
                return exact

        query_tokens = [_variants(token) for token in core]
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

    def matches(self, query: str) -> list[FoodItem]:
        """Every food a plain phrase names: the exact id/name match alone, else all
        token-subset candidates, else nothing. Never a difflib guess -- that path belongs to
        ``resolve``, which refuses; an avoidance excludes every candidate instead
        (child-notes-restrictions design Decision 5)."""
        if query in self._by_id:
            return [self._by_id[query]]
        normalized = _normalize(query)
        exact = self._forms.get(normalized)
        if exact is not None:
            return [exact]
        words = [token for token in normalized.split() if token not in _STOPWORDS]
        core = [token for token in words if not _is_noise(token)] or words
        query_tokens = [_variants(token) for token in core]
        if not query_tokens:
            return []
        return [
            food
            for food, pool in self._token_pools
            if all(variants & pool for variants in query_tokens)
        ]

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

    try:
        _check_unique_ids(table)
    except ValueError as exc:
        raise ValueError(f"Invalid {path}: {exc}") from exc

    logger.info(
        "Loaded food table %s: %d foods (version %s)", path, len(table.foods), table.version
    )
    return LoadedFoodTable(table)


def _check_unique_ids(table: FoodTable) -> None:
    seen: set[str] = set()
    for food in table.foods:
        if food.id in seen:
            raise ValueError(f"food id {food.id!r} is listed twice")
        seen.add(food.id)


def table_from_revision(revision: int, payload: dict) -> LoadedFoodTable:
    """A database snapshot (``{source, foods}``) as the served table, versioned ``db-N``.

    Validated whole exactly like the file; a ``ValueError`` names the offending entry.
    """
    raw = {**payload, "version": f"db-{revision}"}
    try:
        table = FoodTable.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid food table revision {revision}: {_describe(exc, raw)}") from exc
    _check_unique_ids(table)
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


# The served table. Set from the database's latest revision at start-up and after every
# administrative write (one instance, so an in-process swap is exact); until then, or
# without a database, the committed file is served and the log says so.
_TABLE: LoadedFoodTable | None = None


def get_food_table() -> LoadedFoodTable:
    """Process-wide table: the loaded database revision, else the committed file."""
    global _TABLE
    if _TABLE is None:
        _TABLE = load_food_table(DEFAULT_FOOD_TABLE_PATH)
        logger.warning(
            "Serving the committed food table %s (no database table loaded)",
            _TABLE.version,
        )
    return _TABLE


def set_food_table(table: LoadedFoodTable) -> None:
    """Swap the served table atomically (a single assignment; readers keep their snapshot)."""
    global _TABLE
    _TABLE = table


def reset_food_table_cache() -> None:
    """Forget the served table: the next read loads the committed file again."""
    global _TABLE
    _TABLE = None
