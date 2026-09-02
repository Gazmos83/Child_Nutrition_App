"""Intent routing: one tool-calling model call whose ``tool_calls`` are the decision.

Design.md Decisions 1 and 2. ``decide`` binds the nutrient tools plus a ``search_guidelines``
pseudo-tool (the knowledge-base path) and maps the reply to an intent deterministically.
``resolve_context`` is the authority seam: profile-backed arguments come from the request's
child context, never from the model -- Day 6 swaps the request read for an auth-scoped
profile read here and nowhere else.
"""

import datetime as dt
import logging
from collections.abc import Sequence
from enum import Enum
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from backend.chat.prompts import (
    ROUTER_SYSTEM_PROMPT,
    format_child_context,
    format_history,
    format_log_context,
)
from backend.nutrition.feeding import local_date
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
        "notes",
        "activity_level",
    }
)

# Arguments that describe the feeding log. Always filled from the request (change 2 design
# Decision 9): the model must never transcribe a log -- it would drop or invent entries.
LOG_FIELDS = frozenset({"entries", "logged_today", "timezone"})

# Arguments only the service may supply, from its own tool runs; a model-proposed value is
# discarded (a fabricated gap report would steer a plan).
SERVICE_FIELDS = frozenset({"gaps"})


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
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, frozenset | set):
        return sorted(_json_value(v) for v in value)  # type: ignore[type-var]
    if isinstance(value, list | tuple):
        return [_json_value(v) for v in value]
    return value


def today_in(timezone: str) -> dt.date:
    return dt.datetime.now(ZoneInfo(timezone)).date()


def log_context(request: ChatRequest) -> dict[str, object]:
    """The log-backed argument values: every entry, today's entries, the time zone."""
    today = today_in(request.timezone)
    return {
        "entries": [e.model_dump(mode="json") for e in request.feeding_log],
        "logged_today": [
            e.model_dump(mode="json")
            for e in request.feeding_log
            if local_date(e.fed_at, request.timezone) == today
        ],
        "timezone": request.timezone,
    }


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
    model's profile arguments pass through untouched to validation.

    Log-backed fields are always taken from ``request.feeding_log`` -- an empty log is an
    empty list, not the model's guess -- and service-only fields are dropped.
    """
    args = dict(model_args)
    used: list[str] = []
    if args_schema is None:
        return args, used
    fields = set(args_schema.model_fields)

    if request.child is not None:
        for field in sorted(PROFILE_FIELDS & fields):
            value = _json_value(getattr(request.child, field))
            _note_override(tool_name, field, args, value)
            if value is None:
                args.pop(field, None)
                continue
            args[field] = value
            used.append(field)

    log_fields = sorted(LOG_FIELDS & fields)
    if log_fields:
        values = log_context(request)
        for field in log_fields:
            _note_override(tool_name, field, args, values[field])
            args[field] = values[field]
            used.append(field)

    for field in sorted(SERVICE_FIELDS & fields):
        if args.pop(field, None) is not None:
            logger.info("resolve_context tool=%s field=%s model value discarded", tool_name, field)
    return args, used


def _note_override(tool_name: str, field: str, args: dict[str, object], value: object) -> None:
    if field in args and args[field] != value:
        logger.info(
            "resolve_context tool=%s field=%s model=%r context=%r -> context wins",
            tool_name,
            field,
            args[field],
            value,
        )


async def decide(
    chat_model: BaseChatModel, tools: Sequence[BaseTool], request: ChatRequest
) -> RouteDecision:
    """One routing call. The reply's tool calls are the decision; its text is discarded."""
    known = {t.name for t in tools}
    bound = chat_model.bind_tools([*tools, search_guidelines_tool()])
    today = today_in(request.timezone)
    log_line = format_log_context(
        len(request.feeding_log),
        sum(1 for e in request.feeding_log if local_date(e.fed_at, request.timezone) == today),
        request.timezone,
    )
    messages = [
        SystemMessage(
            content=f"{ROUTER_SYSTEM_PROMPT}\n\n{format_child_context(request.child)}\n{log_line}"
        ),
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
