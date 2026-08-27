"""A recording fake chat model for unit tests.

Returns scripted responses, records every prompt it receives, streams word by word, and
can be told to fail -- everything the pipeline tests need, without a network. A scripted
response may be a plain string or a full ``AIMessage`` (for example one carrying
``tool_calls``), and ``bind_tools`` records what was bound and returns the model itself,
so Day 5's router can be exercised offline (Day 5 design.md Decision 8).
"""

from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    if name:
        return str(name)
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("function", {}).get("name") or tool)
    return getattr(tool, "__name__", str(tool))


class RecordingChatModel(BaseChatModel):
    responses: list[str | AIMessage]
    calls: list[list[BaseMessage]] = []
    bound_tools: list[str] = []
    fail_with: str | None = None
    fail_after_tokens: int | None = None

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> RecordingChatModel:
        """Record the bound tool names and return this same model (no real binding)."""
        self.bound_tools.extend(_tool_name(t) for t in tools)
        return self

    def _next(self) -> str | AIMessage:
        if not self.responses:
            raise RuntimeError("RecordingChatModel ran out of scripted responses")
        return self.responses.pop(0)

    @staticmethod
    def _as_message(response: str | AIMessage) -> AIMessage:
        return response if isinstance(response, AIMessage) else AIMessage(content=response)

    @staticmethod
    def _text(response: str | AIMessage) -> str:
        if isinstance(response, str):
            return response
        return response.content if isinstance(response.content, str) else str(response.content)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        return ChatResult(generations=[ChatGeneration(message=self._as_message(self._next()))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self.calls.append(list(messages))
        if self.fail_with and self.fail_after_tokens is None:
            raise RuntimeError(self.fail_with)
        words = self._text(self._next()).split(" ")
        for i, word in enumerate(words):
            if self.fail_after_tokens is not None and i >= self.fail_after_tokens:
                raise RuntimeError(self.fail_with or "stream failed")
            text = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
