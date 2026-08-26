"""A recording fake chat model for unit tests.

Returns scripted responses, records every prompt it receives, streams word by word, and
can be told to fail -- everything the pipeline tests need, without a network.
"""

from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class RecordingChatModel(BaseChatModel):
    responses: list[str]
    calls: list[list[BaseMessage]] = []
    fail_with: str | None = None
    fail_after_tokens: int | None = None

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def _next(self) -> str:
        if not self.responses:
            raise RuntimeError("RecordingChatModel ran out of scripted responses")
        return self.responses.pop(0)

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
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._next()))])

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
        words = self._next().split(" ")
        for i, word in enumerate(words):
            if self.fail_after_tokens is not None and i >= self.fail_after_tokens:
                raise RuntimeError(self.fail_with or "stream failed")
            text = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
