"""Intent routing: one tool-calling model call whose ``tool_calls`` are the decision.

Design.md Decisions 1 and 2. ``decide`` binds the nutrient tools plus a ``search_guidelines``
pseudo-tool (the knowledge-base path) and maps the reply to an intent deterministically.
``resolve_context`` is the authority seam: profile-backed arguments come from the request's
child context, never from the model -- Day 6 swaps the request read for an auth-scoped
profile read here and nowhere else.
"""

import logging
from collections.abc import Sequence
from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from backend.chat.prompts import ROUTER_SYSTEM_PROMPT, format_child_context, format_history
from backend.schemas.chat import ChatRequest, Intent, PlannedCall, RouteDecision

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 4
SEARCH_TOOL_NAME = "search_guidelines"

# Arguments that describe the child. When the request carries child context these are
# filled from it, overriding whatever the model proposed (spec: context is authoritative).
PROFILE_FIELDS = frozenset(
    {
        "age_months",
        "weight_kg",
        "sex",
        "height_cm",
        "allergies",
        "diet_preference",
        "doctors_note",
        "activity_level",
    }
)


class SearchGuidelinesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description=(
            "A standalone search query for the pediatric-guideline knowledge base, with any "
            "pronouns and ages resolved from the conversation."
        ),
    )


def search_guidelines_tool() -> StructuredTool:
    """The knowledge-base path as a tool the model can select. Never executed as a tool:
    the service intercepts the call and runs retrieval itself."""

    def search(query: str) -> str:
        return query

    return StructuredTool.from_function(
        func=search,
        name=SEARCH_TOOL_NAME,
        description=(
            "Search published pediatric nutrition guidelines (WHO, AAP, CDC, USDA/HHS, NIH) "
            "for general information: what foods to start with, how much of a nutrient "
            "children of an age need, safety guidance, and why. Use for any question that "
            "is not a number computed for this specific child."
        ),
        args_schema=SearchGuidelinesInput,
    )


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, frozenset | set):
        return sorted(_json_value(v) for v in value)  # type: ignore[type-var]
    return value


def resolve_context(
    tool_name: str,
    model_args: dict[str, object],
    request: ChatRequest,
    args_schema: type[BaseModel] | None,
) -> tuple[dict[str, object], list[str]]:
    """The arguments a tool actually runs with, and which of them came from the request.

    Profile-backed fields the tool declares are taken from ``request.child``; a value the
    model proposed is replaced (and the mismatch logged). A field the child context does
    not have (e.g. no height recorded) is *removed* so the tool's own required/optional
    rule applies -- the model's invented value never survives. Without child context the
    model's arguments pass through untouched to validation.
    """
    args = dict(model_args)
    used: list[str] = []
    if request.child is None or args_schema is None:
        return args, used
    declared = PROFILE_FIELDS & set(args_schema.model_fields)
    for field in sorted(declared):
        value = _json_value(getattr(request.child, field))
        proposed = args.get(field)
        if field in args and proposed != value:
            logger.info(
                "resolve_context tool=%s field=%s model=%r context=%r -> context wins",
                tool_name,
                field,
                proposed,
                value,
            )
        if value is None:
            args.pop(field, None)
            continue
        args[field] = value
        used.append(field)
    return args, used


async def decide(
    chat_model: BaseChatModel, tools: Sequence[BaseTool], request: ChatRequest
) -> RouteDecision:
    """One routing call. The reply's tool calls are the decision; its text is discarded."""
    known = {t.name for t in tools}
    bound = chat_model.bind_tools([*tools, search_guidelines_tool()])
    messages = [
        SystemMessage(content=f"{ROUTER_SYSTEM_PROMPT}\n\n{format_child_context(request.child)}"),
        *format_history(request.history),
        HumanMessage(content=request.message),
    ]
    reply = await bound.ainvoke(messages)
    tool_calls = list(getattr(reply, "tool_calls", None) or [])

    calls: list[PlannedCall] = []
    planned: list[str] = []
    search_query: str | None = None
    dropped = 0
    for call in tool_calls:
        name = str(call.get("name") or "")
        args = dict(call.get("args") or {})
        if name == SEARCH_TOOL_NAME:
            if search_query is None:
                query = str(args.get("query") or "").strip()
                search_query = query or request.message
                planned.append(name)
            continue
        if name not in known:
            logger.warning("routing proposed unknown tool %r; ignored", name)
            continue
        if len(calls) >= MAX_TOOL_CALLS:
            dropped += 1
            continue
        calls.append(PlannedCall(name=name, args=args, id=call.get("id")))
        planned.append(name)
    if dropped:
        logger.info(
            "routing dropped %d tool call(s) over the cap of %d (kept: %s)",
            dropped,
            MAX_TOOL_CALLS,
            [c.name for c in calls],
        )

    intent: Intent
    if calls and search_query is not None:
        intent = "hybrid"
    elif calls:
        intent = "tool"
    else:
        # Nothing, or only search, selected: the grounded path answers, and an
        # out-of-domain message meets the relevance floor there (Decision 1).
        intent = "rag"
        search_query = search_query if search_query is not None else request.message
    return RouteDecision(
        intent=intent, calls=calls, search_query=search_query, planned=planned, dropped=dropped
    )
