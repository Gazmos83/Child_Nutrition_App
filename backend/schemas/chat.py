"""Request, routing, and response models for ``POST /api/chat`` (chat-api spec).

Two request models since Day 6. ``ChatRequestBody`` is the wire contract: the message,
which of the caller's children it is about, and the conversation so far. ``ChatRequest``
is what the chat service runs on -- the same plus the child's details and feeding log --
and is built server-side from the authenticated account's own rows
(``backend/api/chat.py``). The body cannot carry a child or a log at all, so the stored
profile is the only authority for the numbers a plan is built from (hard rules 8 and 9).
``ChildContext`` reuses the tool schemas' field definitions (ages in months, controlled
vocabularies) so a stored profile can never resolve to what a tool would reject.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.enums import Allergen, DietPreference, Sex
from backend.schemas.rag import Citation, RetrievalMeta, Strategy
from backend.schemas.tools import (
    _AGE,
    _WEIGHT,
    HEIGHT_REQUIRED_FROM_MONTHS,
    MAX_HEIGHT_CM,
    MAX_LOG_ENTRIES,
    MAX_NOTES,
    ActivityLevel,
    FeedingEntry,
    NoteRow,
    TimeZoneName,
    check_unique_notes,
)

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 12

Intent = Literal["rag", "tool", "hybrid"]
ToolStatus = Literal["ok", "error"]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# -- request --------------------------------------------------------------------------------


class ChildContext(_Strict):
    """The child's details as the parent entered them in the side panel.

    Field-for-field the same as ``MealPlanRequest``'s child input, so the same value is
    valid in both places; kept separate because a later change extends the plan request
    with inputs that are not "the child".
    """

    age_months: int = _AGE
    weight_kg: float = _WEIGHT
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    diet_preference: DietPreference = DietPreference.default()
    allergies: frozenset[Allergen] = Field(default_factory=frozenset)
    notes: tuple[NoteRow, ...] = Field(default_factory=tuple, max_length=MAX_NOTES)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> ChildContext:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        check_unique_notes(self.notes)
        return self


class ChatTurn(_Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequestBody(BaseModel):
    """What the browser sends. Unknown fields -- ``child`` included -- are rejected."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    child_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Which of the caller's children the question is about. May be omitted when the "
            "account has exactly one child, or none."
        ),
    )
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    timezone: TimeZoneName = "UTC"
    strategy: Strategy = "advanced"
    stream: bool = True

    @field_validator("message")
    @classmethod
    def _strip_and_require_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatRequest(ChatRequestBody):
    """The resolved request the chat service runs on. Constructed by the server only.

    ``child`` and ``feeding_log`` are read from the authenticated account's rows; the
    log is bounded like the client-held log was, and log-backed tool arguments are filled
    from it, never from the model.
    """

    child: ChildContext | None = None
    feeding_log: list[FeedingEntry] = Field(default_factory=list, max_length=MAX_LOG_ENTRIES)


# -- routing --------------------------------------------------------------------------------


class PlannedCall(_Frozen):
    """One tool invocation the routing step proposed, before context resolution."""

    name: str
    args: dict[str, object] = Field(default_factory=dict)
    id: str | None = None


class RouteDecision(_Frozen):
    intent: Intent
    calls: list[PlannedCall] = Field(description="Nutrient-tool invocations, in order.")
    search_query: str | None = Field(
        default=None, description="Standalone knowledge-base query, when retrieval runs."
    )
    planned: list[str] = Field(description="Every capability selected, in order, by name.")
    dropped: int = Field(default=0, ge=0, description="Invocations over the per-turn cap.")


class ToolActivity(_Frozen):
    """What one tool invocation did, for the tool-activity display and the log."""

    name: str
    status: ToolStatus
    args: dict[str, object] = Field(default_factory=dict)
    used_context: list[str] = Field(
        default_factory=list, description="Argument names filled from the request context."
    )
    result: dict[str, object] | None = Field(
        default=None, description="The tool's result as JSON, when status is 'ok'."
    )
    error: str | None = Field(default=None, description="Parent-facing message on failure.")
    detail: str | None = Field(default=None, description="Technical detail on failure.")


# -- response -------------------------------------------------------------------------------


class ChatResponse(_Frozen):
    answer: str
    intent: Intent
    tools: list[ToolActivity]
    citations: list[Citation]
    retrieval: RetrievalMeta | None
    disclaimer: str
