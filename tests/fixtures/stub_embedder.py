"""A deterministic, offline embedder for tests.

Vectors are bag-of-words hashed into a small fixed dimension and L2-normalised, so two
texts sharing words have higher cosine similarity than two that do not. Good enough to
exercise ranking, filtering, and idempotency without a network.
"""

import hashlib
import math
import re

_WORD = re.compile(r"[a-z0-9]+")


class StubEmbedder:
    def __init__(self, model_name: str = "stub/bag-of-words", dimension: int = 32) -> None:
        self.model_name = model_name
        self._dimension = dimension
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        for word in _WORD.findall(text.lower()):
            digest = hashlib.md5(word.encode()).digest()
            vec[digest[0] % self._dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return [self._embed(t) for t in texts]

    async def embed_query(self, query: str) -> list[float]:
        self.calls += 1
        return self._embed(query)
