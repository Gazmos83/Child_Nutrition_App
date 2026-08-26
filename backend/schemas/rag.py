"""Request and response schemas for RAG answering and ``POST /api/ask``."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Strategy = Literal["basic", "advanced"]


class Citation(BaseModel):
    """One numbered context block, as shown to the model and returned to the client."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=1, description="Number used in the answer text, e.g. [2].")
    source: str = Field(min_length=1, description="Citable source title.")
    year: int | None = Field(default=None, description="Publication year.")
    topic: str | None = None
    section: str | None = None
    document_id: str | None = None
    score: float | None = Field(default=None, description="Cosine similarity to the query.")
    excerpt: str = Field(default="", description="The passage text placed in context.")


class RetrievalMeta(BaseModel):
    """What retrieval did, for evaluation and the tool-activity display."""

    model_config = ConfigDict(frozen=True)

    strategy: Strategy
    queries: list[str] = Field(description="Every query issued to the knowledge base.")
    filters: dict[str, object] = Field(
        default_factory=dict, description="Metadata filters applied (validated values only)."
    )
    filter_dropped: bool = Field(
        default=False,
        description="True if the age filter eliminated everything and was retried without.",
    )
    retrieved: int = Field(
        ge=0, description="Passages returned by the knowledge base after fusion/dedup."
    )
    kept: int = Field(
        ge=0, description="Passages that passed the relevance floor and fit the context budget."
    )
    top_score: float | None = Field(default=None, description="Best cosine similarity seen.")


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    strategy: Strategy = "advanced"
    stream: bool = True

    @field_validator("question")
    @classmethod
    def _strip_and_require_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class AskResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[Citation]
    disclaimer: str
    strategy: Strategy
    retrieval: RetrievalMeta
