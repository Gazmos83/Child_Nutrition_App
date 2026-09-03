"""Live, whitelisted, third-party nutrition lookup (CLAUDE.md hard rule 10).

Used only when the internal food table misses. Every source here is closed and
centrally configured (``ExternalFoodSettings.external_food_domains``) -- a lookup never
calls a URL the code did not already know about. Parsing is deterministic code, never the
LLM (hard rule 2): a source that does not match the expected shape raises, it never
fabricates a number. :func:`lookup_external_food` itself never raises -- a lookup problem
must never break a chat turn -- so every exception here is for the fetch functions and
tests to reason about, not for chat code to catch.

USDA FoodData Central (a documented, versioned JSON API, and this app's own stated default
data provenance -- see ``nutrition-data/foods.yaml``) is tried first. MyFoodData has no
documented API; ``_fetch_myfooddata`` scrapes its nutrition-facts page and its selectors are
UNVERIFIED against the live site. Its hostname must not be added to
``EXTERNAL_FOOD_DOMAINS`` until its Terms of Service and robots.txt have been checked.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import ExternalFoodSettings, get_external_food_settings

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 200


class ExternalLookupError(Exception):
    """Base for every typed failure a source's fetch function may raise."""


class ExternalLookupDisabled(ExternalLookupError):
    pass


class ExternalLookupDomainNotAllowed(ExternalLookupError):
    def __init__(self, hostname: str) -> None:
        super().__init__(f"{hostname!r} is not in EXTERNAL_FOOD_DOMAINS")
        self.hostname = hostname


class ExternalLookupNotFound(ExternalLookupError):
    def __init__(self, query: str) -> None:
        super().__init__(f"no match for {query!r}")
        self.query = query


class ExternalLookupParseError(ExternalLookupError):
    """The response did not have the shape a source's parser expects.

    Raised instead of guessing -- a missing or renamed field must never become a fabricated
    zero (hard rule 2).
    """


class ExternalLookupUnavailable(ExternalLookupError):
    """Timeout, network failure, or a non-2xx response."""


def _sanitize_text(text: str | None) -> str | None:
    """Collapse whitespace and cap length.

    This text is third-party, untrusted content (a page title, a search match). It must
    stay short and inert -- never long enough, or free-form enough, to read as instructions
    if it were ever placed near a model prompt. Callers keep it out of the model's context
    entirely (see ``backend/chat/service.py``); this is defense in depth, not the only guard.
    """
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return None
    return collapsed[:_MAX_TEXT_LEN]


def _normalize_query(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class ExternalSource(StrEnum):
    """The closed set of sources a lookup may use. Not open-ended: adding one is a
    reviewed code change, not a runtime configuration value (hard rule 10)."""

    USDA_FDC = "usda_fdc"
    MYFOODDATA = "myfooddata"


class ExternalNutrientValues(BaseModel):
    """Only the macro fields the food table itself requires (``FoodItem``'s required six).

    ``None`` means "not reported by this source", the same convention as the table's own
    optional micronutrients -- never a fabricated zero.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carbohydrate_g: float | None = Field(default=None, ge=0)
    iron_mg: float | None = Field(default=None, ge=0)
    calcium_mg: float | None = Field(default=None, ge=0)


class ExternalFoodResult(BaseModel):
    """One external match: nutrients plus enough provenance to cite and, for an admin, to
    prefill an approval form. Never itself a ``FoodItem`` -- it carries no safety metadata
    and is not usable in a meal plan (hard rule 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    matched_name: str
    source: ExternalSource
    source_label: str
    source_url: str
    retrieved_at: datetime
    serving_description: str | None = None
    nutrients: ExternalNutrientValues


FetchFn = Callable[[str, ExternalFoodSettings, httpx.AsyncClient | None], Awaitable[ExternalFoodResult]]


@dataclass(frozen=True)
class SourceConfig:
    hostname: str
    label: str
    fetch: FetchFn


# -- USDA FoodData Central ------------------------------------------------------------------

_USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# Documented, stable USDA nutrient ids (https://fdc.nal.usda.gov), mapped to the table's
# own field names. USDA's Foundation/SR Legacy values are per 100 g, matching this app's
# convention for imported data.
_USDA_NUTRIENT_IDS: dict[int, str] = {
    1008: "calories",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbohydrate_g",
    1089: "iron_mg",
    1087: "calcium_mg",
}


def _parse_usda_food(query: str, payload: dict) -> ExternalFoodResult:
    foods = payload.get("foods")
    if not isinstance(foods, list) or not foods:
        raise ExternalLookupNotFound(query)
    food = foods[0]
    if not isinstance(food, dict):
        raise ExternalLookupParseError("foods[0] was not an object")
    nutrients_raw = food.get("foodNutrients")
    if not isinstance(nutrients_raw, list):
        raise ExternalLookupParseError("foodNutrients missing or not a list")
    values: dict[str, float] = {}
    for entry in nutrients_raw:
        if not isinstance(entry, dict):
            continue
        nutrient_id = entry.get("nutrientId")
        field = _USDA_NUTRIENT_IDS.get(nutrient_id)
        if field is None:
            continue
        value = entry.get("value")
        if isinstance(value, int | float) and value >= 0:
            values[field] = float(value)
    name = food.get("description")
    if not isinstance(name, str) or not name.strip():
        raise ExternalLookupParseError("food description missing")
    return ExternalFoodResult(
        query=query,
        matched_name=_sanitize_text(name) or query,
        source=ExternalSource.USDA_FDC,
        source_label=_SOURCE_CONFIG[ExternalSource.USDA_FDC].label,
        source_url=f"https://fdc.nal.usda.gov/food-details/{food.get('fdcId', '')}",
        retrieved_at=datetime.now(UTC),
        serving_description="per 100 g",
        nutrients=ExternalNutrientValues(**values),
    )


async def _fetch_usda(
    query: str, settings: ExternalFoodSettings, client: httpx.AsyncClient | None = None
) -> ExternalFoodResult:
    if not settings.usda_fdc_api_key:
        raise ExternalLookupUnavailable("USDA_FDC_API_KEY is not configured")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.external_food_timeout_seconds)
    try:
        response = await client.get(
            _USDA_SEARCH_URL,
            params={
                "query": query,
                "api_key": settings.usda_fdc_api_key,
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
            },
        )
    except httpx.HTTPError as exc:
        raise ExternalLookupUnavailable(str(exc)) from exc
    finally:
        if owns_client:
            await client.aclose()
    if response.status_code != 200:
        raise ExternalLookupUnavailable(f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalLookupParseError(f"response was not JSON: {exc}") from exc
    return _parse_usda_food(query, payload)


# -- MyFoodData (no documented API -- HTML scrape; UNVERIFIED selectors) --------------------

_MYFOODDATA_SEARCH_URL = "https://tools.myfooddata.com/nutrition-facts"

# UNVERIFIED against the live site. These labels are a best guess at MyFoodData's
# nutrition-facts table; check them (and the site's Terms of Service / robots.txt) before
# ever adding "tools.myfooddata.com" to EXTERNAL_FOOD_DOMAINS.
_MYFOODDATA_LABELS: dict[str, str] = {
    "Calories": "calories",
    "Protein": "protein_g",
    "Total Fat": "fat_g",
    "Carbohydrates": "carbohydrate_g",
    "Iron": "iron_mg",
    "Calcium": "calcium_mg",
}


def _parse_myfooddata_html(query: str, html: str) -> ExternalFoodResult:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find(["h1", "h2"])
    if title is None or not title.get_text(strip=True):
        raise ExternalLookupParseError(f"no title found for {query!r}")
    values: dict[str, float] = {}
    for label, field in _MYFOODDATA_LABELS.items():
        cell = soup.find(string=re.compile(rf"^\s*{re.escape(label)}\s*$"))
        if cell is None:
            continue
        row = cell.find_parent(["tr", "li", "div"])
        if row is None:
            continue
        match = re.search(r"[\d.]+", row.get_text())
        if match:
            values[field] = float(match.group())
    if not values:
        raise ExternalLookupParseError(f"no recognizable nutrient values for {query!r}")
    return ExternalFoodResult(
        query=query,
        matched_name=_sanitize_text(title.get_text()) or query,
        source=ExternalSource.MYFOODDATA,
        source_label=_SOURCE_CONFIG[ExternalSource.MYFOODDATA].label,
        source_url=_MYFOODDATA_SEARCH_URL,
        retrieved_at=datetime.now(UTC),
        serving_description=None,
        nutrients=ExternalNutrientValues(**values),
    )


async def _fetch_myfooddata(
    query: str, settings: ExternalFoodSettings, client: httpx.AsyncClient | None = None
) -> ExternalFoodResult:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.external_food_timeout_seconds)
    try:
        response = await client.get(_MYFOODDATA_SEARCH_URL, params={"q": query})
    except httpx.HTTPError as exc:
        raise ExternalLookupUnavailable(str(exc)) from exc
    finally:
        if owns_client:
            await client.aclose()
    if response.status_code == 404:
        raise ExternalLookupNotFound(query)
    if response.status_code != 200:
        raise ExternalLookupUnavailable(f"HTTP {response.status_code}")
    return _parse_myfooddata_html(query, response.text)


_SOURCE_CONFIG: dict[ExternalSource, SourceConfig] = {
    ExternalSource.USDA_FDC: SourceConfig(
        hostname="api.nal.usda.gov", label="USDA FoodData Central", fetch=_fetch_usda
    ),
    ExternalSource.MYFOODDATA: SourceConfig(
        hostname="tools.myfooddata.com", label="MyFoodData", fetch=_fetch_myfooddata
    ),
}

# Sources are tried in this order; USDA (documented, versioned, already-trusted) first.
_SOURCE_ORDER: tuple[ExternalSource, ...] = (ExternalSource.USDA_FDC, ExternalSource.MYFOODDATA)


def is_domain_allowed(hostname: str, settings: ExternalFoodSettings) -> bool:
    """Exact, case-insensitive match only -- never a suffix/subdomain match, which would
    admit ``tools.myfooddata.com.evil.example`` alongside the real host."""
    return hostname.lower() in settings.external_food_domains


# -- cache ------------------------------------------------------------------------------

_CacheKey = tuple[str, str]
_CACHE: OrderedDict[_CacheKey, tuple[float, ExternalFoodResult | None]] = OrderedDict()
_LOCKS: dict[_CacheKey, asyncio.Lock] = {}
_SENTINEL = object()
# A miss is worth remembering too (so a repeated bad query does not refetch every turn), but
# for a fraction of the TTL a real match gets -- a source correcting itself should recover
# faster than a genuine value going stale.
_MISS_TTL_FRACTION = 0.1


def _cache_get(key: _CacheKey) -> ExternalFoodResult | None | object:
    entry = _CACHE.get(key)
    if entry is None:
        return _SENTINEL
    expires_at, result = entry
    if time.monotonic() >= expires_at:
        del _CACHE[key]
        return _SENTINEL
    _CACHE.move_to_end(key)
    return result


def _cache_set(key: _CacheKey, result: ExternalFoodResult | None, settings: ExternalFoodSettings) -> None:
    ttl = settings.external_food_cache_ttl_seconds
    if result is None:
        ttl = ttl * _MISS_TTL_FRACTION
    _CACHE[key] = (time.monotonic() + ttl, result)
    _CACHE.move_to_end(key)
    while len(_CACHE) > settings.external_food_cache_max_entries:
        _CACHE.popitem(last=False)


def _lock_for(key: _CacheKey) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def reset_external_lookup_cache() -> None:
    """Forget every cached result and lock. Test-only, matching
    ``reset_food_table_cache()``'s naming convention."""
    _CACHE.clear()
    _LOCKS.clear()


# -- entry point --------------------------------------------------------------------------


async def lookup_external_food(
    query: str, settings: ExternalFoodSettings | None = None
) -> ExternalFoodResult | None:
    """The first whitelisted source's match for ``query``, or ``None``.

    Never raises: disabled, unconfigured, not whitelisted, not found, or a source failure
    all return ``None`` so a lookup problem can never break a chat turn. Tries USDA first,
    then MyFoodData, each only if its hostname is in ``external_food_domains``.
    """
    settings = settings or get_external_food_settings()
    if not settings.external_food_lookup_enabled:
        return None
    normalized = _normalize_query(query)
    if not normalized:
        return None
    for source in _SOURCE_ORDER:
        config = _SOURCE_CONFIG[source]
        if not is_domain_allowed(config.hostname, settings):
            continue
        cache_key = (source.value, normalized)
        cached = _cache_get(cache_key)
        if cached is not _SENTINEL:
            if cached is not None:
                return cached
            continue
        async with _lock_for(cache_key):
            cached = _cache_get(cache_key)
            if cached is not _SENTINEL:
                result = cached
            else:
                try:
                    result = await config.fetch(query, settings, None)
                except ExternalLookupError as exc:
                    logger.info(
                        "external lookup miss source=%s reason=%s", source.value, type(exc).__name__
                    )
                    result = None
                except Exception:
                    logger.exception("external lookup failed source=%s", source.value)
                    result = None
                _cache_set(cache_key, result, settings)
        if result is not None:
            return result
    return None
