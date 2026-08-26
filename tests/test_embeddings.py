"""EmbeddingProvider: one explicit OpenRouter model, no fallback (Day 3 task 2.1)."""

import sys
from pathlib import Path

import pytest

from backend.core.config import OPENROUTER_BASE_URL, RAGSettings
from backend.knowledge.embeddings import KNOWN_DIMENSIONS, EmbeddingProvider


class TestConstruction:
    def test_missing_key_names_the_setting(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            EmbeddingProvider(model="openai/text-embedding-3-small", api_key=None)
        assert "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_empty_key_is_missing(self) -> None:
        with pytest.raises(RuntimeError):
            EmbeddingProvider(model="openai/text-embedding-3-small", api_key="")

    def test_from_settings_without_key_names_the_setting(self) -> None:
        settings = RAGSettings(openrouter_api_key=None, _env_file=None)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            EmbeddingProvider.from_settings(settings)

    def test_construction_is_offline(self) -> None:
        """Building the provider must not call the network; only the first embed does."""
        provider = EmbeddingProvider(model="openai/text-embedding-3-small", api_key="sk-test")
        assert provider.model_name == "openai/text-embedding-3-small"
        assert provider.dimension == KNOWN_DIMENSIONS["openai/text-embedding-3-small"] == 1536

    def test_points_at_openrouter(self) -> None:
        provider = EmbeddingProvider(model="openai/text-embedding-3-small", api_key="sk-test")
        assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
        assert str(provider._embedder.openai_api_base) == OPENROUTER_BASE_URL
        # OpenRouter takes strings, not OpenAI's pre-tokenised input.
        assert provider._embedder.check_embedding_ctx_length is False

    def test_unknown_model_dimension_is_measured_later(self) -> None:
        provider = EmbeddingProvider(model="qwen/qwen3-embedding-4b", api_key="sk-test")
        assert provider.dimension is None
        provider._record_dimension([0.0] * 2560)
        assert provider.dimension == 2560
        with pytest.raises(RuntimeError, match="2560"):
            provider._record_dimension([0.0] * 3)


class TestNoLocalFallback:
    def test_sentence_transformers_is_not_imported(self) -> None:
        """Decision 3: the Day 2 fallback is gone, not merely disabled."""
        import backend.knowledge.embeddings as module

        assert "sentence_transformers" not in sys.modules
        assert "SentenceTransformer" not in Path(module.__file__).read_text()

    async def test_empty_inputs_short_circuit_without_network(self) -> None:
        provider = EmbeddingProvider(model="openai/text-embedding-3-small", api_key="sk-test")
        assert await provider.embed_texts([]) == []
        assert await provider.embed_query("") == []
