"""Request, routing, and response models for ``POST /api/chat`` (Day 5 chat-api spec).

The child's details travel in the request body (design.md Decisions 2 and 7): nothing
here is read from a database and no identity is taken, so hard rule 9 holds because no
user-scoped operation exists. ``ChildContext`` reuses the tool schemas' field definitions
(ages in months, controlled vocabularies) so the form cannot send what a tool would reject.
"""

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
    ActivityLevel,
    FeedingEntry,
    TimeZoneName,
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
    doctors_note: str | None = Field(default=None, max_length=4000)
    activity_level: ActivityLevel = ActivityLevel.LOW_ACTIVE

    @model_validator(mode="after")
    def _normalise(self) -> ChildContext:
        if self.age_months >= HEIGHT_REQUIRED_FROM_MONTHS and self.height_cm is None:
            raise ValueError(
                f"height_cm is required from {HEIGHT_REQUIRED_FROM_MONTHS} months: the DRI "
                "energy equation for 3–8 years uses height"
            )
        if self.doctors_note is not None and not self.doctors_note.strip():
            object.__setattr__(self, "doctors_note", None)
        return self


class ChatTurn(_Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    child: ChildContext | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    # Change 2: the feeding log is client-held until Day 6 and travels with every message,
    # bounded; log-backed tool arguments are filled from it, never from the model.
    feeding_log: list[FeedingEntry] = Field(default_factory=list, max_length=MAX_LOG_ENTRIES)
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
