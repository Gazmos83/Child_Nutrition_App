"""``backend/nutrition/external_lookup.py`` (CLAUDE.md hard rule 10)."""

import httpx
import pytest

from backend.core.config import ExternalFoodSettings
from backend.nutrition.external_lookup import (
    _SOURCE_CONFIG,
    ExternalLookupNotFound,
    ExternalLookupParseError,
    ExternalSource,
    SourceConfig,
    _fetch_usda,
    _parse_usda_food,
    is_domain_allowed,
    lookup_external_food,
    reset_external_lookup_cache,
)

USDA_HOST = "api.nal.usda.gov"
MYFOODDATA_HOST = "tools.myfooddata.com"


def settings(**overrides) -> ExternalFoodSettings:
    return ExternalFoodSettings(
        **{
            "external_food_lookup_enabled": True,
            "external_food_domains": [USDA_HOST],
            "usda_fdc_api_key": "test-key",
            **overrides,
        }
    )


@pytest.fixture(autouse=True)
def clean_cache():
    reset_external_lookup_cache()
    yield
    reset_external_lookup_cache()


def usda_payload(**nutrient_overrides) -> dict:
    values = {
        1008: 52.0,
        1003: 0.3,
        1004: 0.2,
        1005: 13.8,
        1089: 0.12,
        1087: 6.0,
        **nutrient_overrides,
    }
    return {
        "foods": [
            {
                "description": "Apple, raw",
                "fdcId": 1102644,
                "foodNutrients": [{"nutrientId": k, "value": v} for k, v in values.items()],
            }
        ]
    }


class TestDomainWhitelist:
    def test_exact_match_is_allowed(self) -> None:
        assert is_domain_allowed(USDA_HOST, settings())

    def test_unlisted_host_is_refused(self) -> None:
        assert not is_domain_allowed(MYFOODDATA_HOST, settings())

    def test_suffix_spoof_is_refused(self) -> None:
        """A suffix match would admit an attacker-controlled host; only exact equality
        may pass (hard rule 10)."""
        spoofed = f"{USDA_HOST}.evil.example"
        assert not is_domain_allowed(spoofed, settings())  # whitelist has USDA_HOST, not this

    def test_case_insensitive(self) -> None:
        assert is_domain_allowed(USDA_HOST, settings(external_food_domains=[USDA_HOST.upper()]))

    async def test_disabled_short_circuits_regardless_of_whitelist(self) -> None:
        disabled = settings(external_food_lookup_enabled=False)
        assert await lookup_external_food("apple", disabled) is None


class TestUsdaParsing:
    def test_parses_the_required_macro_fields(self) -> None:
        result = _parse_usda_food("apple", usda_payload())
        assert result.matched_name == "Apple, raw"
        assert result.source is ExternalSource.USDA_FDC
        assert result.nutrients.calories == 52.0
        assert result.nutrients.protein_g == 0.3
        assert result.nutrients.iron_mg == 0.12

    def test_unrecognized_nutrient_ids_are_ignored_not_fabricated(self) -> None:
        payload = usda_payload()
        payload["foods"][0]["foodNutrients"].append({"nutrientId": 9999, "value": 1.0})
        result = _parse_usda_food("apple", payload)
        assert result.nutrients.calories == 52.0  # unaffected

    def test_empty_results_raise_not_found(self) -> None:
        with pytest.raises(ExternalLookupNotFound):
            _parse_usda_food("nonexistent", {"foods": []})

    def test_missing_food_nutrients_key_raises_parse_error_never_fabricates(self) -> None:
        with pytest.raises(ExternalLookupParseError):
            _parse_usda_food("apple", {"foods": [{"description": "Apple", "fdcId": 1}]})

    def test_missing_description_raises_parse_error(self) -> None:
        with pytest.raises(ExternalLookupParseError):
            _parse_usda_food("apple", {"foods": [{"fdcId": 1, "foodNutrients": []}]})


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _patch_usda_fetch(monkeypatch, handler) -> list[httpx.Request]:
    """Route the USDA source through a mock transport, bypassing real network access.

    ``_SOURCE_CONFIG`` binds ``fetch`` once at import time, so patching the module-level
    ``_fetch_usda`` name has no effect on it -- the registry entry itself must be replaced.
    """
    calls: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    client = _client(recording_handler)

    async def patched(query: str, settings: ExternalFoodSettings, client_arg=None):
        return await _fetch_usda(query, settings, client=client)

    original = _SOURCE_CONFIG[ExternalSource.USDA_FDC]
    monkeypatch.setitem(
        _SOURCE_CONFIG,
        ExternalSource.USDA_FDC,
        SourceConfig(hostname=original.hostname, label=original.label, fetch=patched),
    )
    return calls


class TestFetchAndCache:
    async def test_fetch_usda_hits_the_mock_transport(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=usda_payload())

        result = await _fetch_usda("apple", settings(), client=_client(handler))
        assert result.matched_name == "Apple, raw"
        assert len(calls) == 1

    async def test_lookup_caches_a_hit_within_ttl(self, monkeypatch) -> None:
        calls = _patch_usda_fetch(
            monkeypatch, lambda request: httpx.Response(200, json=usda_payload())
        )
        s = settings()
        first = await lookup_external_food("apple", s)
        second = await lookup_external_food("apple", s)
        assert first is not None and second is not None
        assert first.matched_name == second.matched_name
        assert len(calls) == 1  # the second call was served from cache

    async def test_lookup_caches_a_miss_too(self, monkeypatch) -> None:
        calls = _patch_usda_fetch(
            monkeypatch, lambda request: httpx.Response(200, json={"foods": []})
        )
        s = settings()
        first = await lookup_external_food("nonexistent", s)
        second = await lookup_external_food("nonexistent", s)
        assert first is None and second is None
        assert len(calls) == 1

    async def test_source_failure_returns_none_never_raises(self, monkeypatch) -> None:
        _patch_usda_fetch(monkeypatch, lambda request: httpx.Response(500))
        assert await lookup_external_food("apple", settings()) is None

    async def test_cache_bound_evicts_the_oldest_entry(self, monkeypatch) -> None:
        _patch_usda_fetch(monkeypatch, lambda request: httpx.Response(200, json=usda_payload()))
        s = settings(external_food_cache_max_entries=2)
        await lookup_external_food("apple", s)
        await lookup_external_food("banana", s)
        await lookup_external_food("cherry", s)
        from backend.nutrition.external_lookup import _CACHE

        assert len(_CACHE) <= 2
