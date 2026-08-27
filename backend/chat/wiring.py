"""Process-wide ``ChatService`` built from the Day 3 pipeline and the Day 4 tools.

Mirrors ``backend/rag/llm.py``: nothing runs at import time; the first call builds and
caches. The doctor's-note extraction inside ``generate_meal_plan`` uses the same chat model
as routing and answering.
"""

from functools import lru_cache

from backend.chat.service import ChatService
from backend.rag.llm import get_pipeline
from backend.tools.langchain_tools import build_tools


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    """Process-wide service, built on first use. Raises ``RuntimeError`` if unconfigured."""
    pipeline = get_pipeline()
    return ChatService(pipeline, pipeline.chat_model, build_tools(pipeline.chat_model))


def reset_chat_service_cache() -> None:
    """For tests that rebind configuration."""
    get_chat_service.cache_clear()
