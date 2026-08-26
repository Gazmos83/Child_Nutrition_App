"""Provider wiring is lazy and fails loudly without a key (task 5.6)."""

import socket

import pytest

from backend.core.config import OPENROUTER_BASE_URL, RAGSettings


class TestBuildChatModel:
    def test_missing_key_names_the_setting(self) -> None:
        from backend.rag.llm import build_chat_model, build_pipeline

        settings = RAGSettings(openrouter_api_key=None, _env_file=None)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_chat_model(settings)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_pipeline(settings)

    def test_points_at_openrouter_with_temperature_zero(self) -> None:
        from backend.rag.llm import build_chat_model

        model = build_chat_model(RAGSettings(openrouter_api_key="sk-test", _env_file=None))
        assert model.openai_api_base == OPENROUTER_BASE_URL
        assert model.temperature == 0
        assert model.model_name == "openai/gpt-4o-mini"

    def test_build_pipeline_is_offline(self, monkeypatch) -> None:
        """Constructing the pipeline must not open a socket; only requests do."""
        from backend.rag.llm import build_pipeline

        def no_network(*args, **kwargs):
            raise AssertionError("network access during pipeline construction")

        monkeypatch.setattr(socket.socket, "connect", no_network)
        pipeline = build_pipeline(RAGSettings(openrouter_api_key="sk-test", _env_file=None))
        assert set(pipeline.retrievers) == {"basic", "advanced"}
        assert pipeline.retrievers["basic"].name == "basic"
        assert pipeline.retrievers["advanced"].name == "advanced"


def test_importing_backend_rag_is_offline(monkeypatch) -> None:
    import importlib
    import sys

    def no_network(*args, **kwargs):
        raise AssertionError("network access at import time")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    for name in [m for m in sys.modules if m.startswith("backend.rag")]:
        del sys.modules[name]
    importlib.import_module("backend.rag.llm")
    importlib.import_module("backend.rag.pipeline")
