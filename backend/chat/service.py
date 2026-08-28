"""Execute a routing decision and compose the answer (design.md Decisions 3, 5, 6).

``run_tools`` runs each planned invocation through its LangChain tool -- so the tool's own
Pydantic schema validates the arguments -- and turns every failure into a ``ToolActivity``
the parent can read. ``ChatService.stream`` yields typed events in the order the API sends
them: ``route``, ``tool``..., ``token``..., ``final``, ``done``. The ``rag`` path delegates
to the Day 3 pipeline unchanged; ``tool``/``hybrid`` answers use the tools prompt.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from backend.chat import copy
from backend.chat.prompts import ANSWER_WITH_TOOLS_SYSTEM_PROMPT, build_tools_answer_prompt
from backend.chat.router import PROFILE_FIELDS, decide, resolve_context
from backend.nutrition.foods import FoodNotFoundError
from backend.nutrition.safety import UnsafePlanError
from backend.rag.pipeline import RagPipeline, RagResponse, RetrievedContext
from backend.rag.prompts import DISCLAIMER
from backend.rag.retrievers import _content_text
from backend.schemas.chat import (
    ChatRequest,
    ChatResponse,
    PlannedCall,
    RouteDecision,
    ToolActivity,
)
from backend.schemas.rag import Citation, RetrievalMeta

logger = logging.getLogger(__name__)
route_logger = logging.getLogger("backend.chat.router")
tool_logger = logging.getLogger("backend.chat.tools")

# Change 2 design Decision 9: a plan over a non-empty log is always informed by gap detection
# -- the model's if it planned one, otherwise the service's own run, made before the plan.
PLAN_TOOL = "generate_meal_plan"
GAPS_TOOL = "detect_nutrient_gaps"


@dataclass(frozen=True)
class ChatEvent:
    event: str
    data: dict[str, object]


# -- tool execution -------------------------------------------------------------------------


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    loc = ".".join(str(p) for p in first["loc"]) or "value"
    return f"{loc}: {first['msg']}"


def _validation_message(exc: ValidationError, request: ChatRequest) -> str:
    """The parent-facing line for a rejected argument set (design.md Decision 5)."""
    errors = exc.errors()
    missing = [str(e["loc"][0]) for e in errors if e["type"] == "missing" and e["loc"]]
    profile_missing = [f for f in missing if f in PROFILE_FIELDS]
    height_rule = any("height_cm is required" in e["msg"] for e in errors)
    if request.child is None and (profile_missing or height_rule):
        return copy.MISSING_CHILD_INFO_HINT
    if missing:
        return copy.missing_field_hint(missing[0])
    if height_rule:
        return copy.missing_field_hint("height_cm")
    return copy.TOOL_FAILED


def _as_json(result: object) -> dict[str, object]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return json.loads(json.dumps(result, default=str))
    return {"value": json.loads(json.dumps(result, default=str))}


async def _run_one(
    name: str,
    model_args: dict[str, object],
    request: ChatRequest,
    tool: BaseTool,
    inject: dict[str, object] | None = None,
) -> ToolActivity:
    schema = tool.args_schema if isinstance(tool.args_schema, type) else None
    args, used = resolve_context(name, model_args, request, schema)
    if inject:
        args.update(inject)
        used.extend(inject)
    started = time.perf_counter()
    activity = await _invoke(name, args, used, request, tool)
    # One record per invocation (observability spec): outcome and latency, and which
    # arguments came from the child's stored details or log -- never the values.
    tool_logger.info(
        "tool %s %s %dms",
        name,
        activity.status,
        int((time.perf_counter() - started) * 1000),
        extra={
            "tool": name,
            "status": activity.status,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "used_context": list(used),
            "error_kind": _error_kind(activity),
        },
    )
    return activity


def _error_kind(activity: ToolActivity) -> str | None:
    if activity.status == "ok":
        return None
    if activity.error == copy.SAFETY_STOP:
        return "unsafe"
    if activity.error == copy.TOOL_FAILED:
        return "failure"
    if activity.detail and activity.detail.startswith("Unknown food"):
        return "unknown_food"
    return "validation"


async def _invoke(
    name: str,
    args: dict[str, object],
    used: list[str],
    request: ChatRequest,
    tool: BaseTool,
) -> ToolActivity:
    try:
        result = await tool.ainvoke(args)
    except ValidationError as exc:
        return ToolActivity(
            name=name,
            status="error",
            args=args,
            used_context=used,
            error=_validation_message(exc, request),
            detail=_first_error(exc),
        )
    except FoodNotFoundError as exc:
        return ToolActivity(
            name=name,
            status="error",
            args=args,
            used_context=used,
            error=copy.unknown_food(exc.food_id),
            detail=str(exc),
        )
    except UnsafePlanError as exc:
        logger.error("tool %s raised UnsafePlanError: %s", name, exc)
        return ToolActivity(
            name=name,
            status="error",
            args=args,
            used_context=used,
            error=copy.SAFETY_STOP,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return ToolActivity(
            name=name,
            status="error",
            args=args,
            used_context=used,
            error=copy.TOOL_FAILED,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return ToolActivity(
        name=name, status="ok", args=args, used_context=used, result=_as_json(result)
    )


async def run_tools(
    decision: RouteDecision, request: ChatRequest, tools: dict[str, BaseTool]
) -> list[ToolActivity]:
    """Run the planned invocations; results keep the planned order, planner last.

    Everything but ``generate_meal_plan`` runs concurrently. When a plan is planned and the
    request carries a feeding log, gap detection runs first (the model's call if it made
    one, otherwise an implicit one) and its report is handed to the planner as ``gaps``.
    """
    planners = [c for c in decision.calls if c.name == PLAN_TOOL]
    others = [c for c in decision.calls if c.name != PLAN_TOOL]
    if (
        planners
        and request.feeding_log
        and GAPS_TOOL in tools
        and not any(c.name == GAPS_TOOL for c in others)
    ):
        others.append(PlannedCall(name=GAPS_TOOL, args={}))
    activities = list(
        await asyncio.gather(*(_run_one(c.name, c.args, request, tools[c.name]) for c in others))
    )
    if planners:
        report = next((a for a in activities if a.name == GAPS_TOOL and a.status == "ok"), None)
        inject = {"gaps": report.result} if report is not None else None
        activities.extend(
            await asyncio.gather(
                *(_run_one(c.name, c.args, request, tools[c.name], inject) for c in planners)
            )
        )
    return activities


# -- the service ----------------------------------------------------------------------------


class ChatService:
    def __init__(
        self, pipeline: RagPipeline, chat_model: BaseChatModel, tools: Sequence[BaseTool]
    ) -> None:
        self.pipeline = pipeline
        self.chat_model = chat_model
        self.tools = list(tools)
        self.tools_by_name = {t.name: t for t in self.tools}

    def _final(
        self,
        intent: str,
        activities: list[ToolActivity],
        citations: list[Citation],
        retrieval: RetrievalMeta | None,
    ) -> ChatEvent:
        return ChatEvent(
            "final",
            {
                "citations": [c.model_dump(mode="json") for c in citations],
                "retrieval": retrieval.model_dump(mode="json") if retrieval else None,
                "disclaimer": DISCLAIMER,
                "intent": intent,
                "tools": [{"name": a.name, "status": a.status} for a in activities],
            },
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        decision = await decide(self.chat_model, self.tools, request)
        yield ChatEvent("route", {"intent": decision.intent, "planned": decision.planned})

        activities = await run_tools(decision, request, self.tools_by_name)
        for activity in activities:
            yield ChatEvent("tool", activity.model_dump(mode="json"))

        retrieval: RetrievalMeta | None = None
        if decision.intent == "rag":
            query = decision.search_query or request.message
            async for item in self.pipeline.stream(query, request.strategy):
                if isinstance(item, RagResponse):
                    retrieval = item.retrieval
                    yield self._final("rag", activities, item.citations, item.retrieval)
                else:
                    yield ChatEvent("token", {"text": item})
        else:
            retrieved: RetrievedContext | None = None
            if decision.search_query is not None:
                retrieved = await self.pipeline.retrieve(decision.search_query, request.strategy)
                retrieval = self.pipeline.retrieval_meta(retrieved, request.strategy)
            context = retrieved.context if retrieved and retrieved.citations else ""
            citations = retrieved.citations if retrieved else []
            messages = [
                SystemMessage(content=ANSWER_WITH_TOOLS_SYSTEM_PROMPT),
                HumanMessage(
                    content=build_tools_answer_prompt(request.message, context, activities)
                ),
            ]
            async for chunk in self.chat_model.astream(messages):
                text = _content_text(chunk.content)
                if text:
                    yield ChatEvent("token", {"text": text})
            yield self._final(decision.intent, activities, citations, retrieval)

        latency_ms = int((time.perf_counter() - started) * 1000)
        # The message's length, never its text (observability spec).
        route_logger.info(
            "chat intent=%s planned=%s executed=%s dropped=%d retrieval_kept=%s "
            "retrieval_top=%s message_chars=%d latency_ms=%d",
            decision.intent,
            decision.planned,
            [f"{a.name}:{a.status}" for a in activities],
            decision.dropped,
            retrieval.kept if retrieval else "-",
            f"{retrieval.top_score:.3f}" if retrieval and retrieval.top_score is not None else "-",
            len(request.message),
            latency_ms,
            extra={
                "intent": decision.intent,
                "planned": list(decision.planned),
                "executed": [f"{a.name}:{a.status}" for a in activities],
                "dropped": decision.dropped,
                "retrieval_kept": retrieval.kept if retrieval else None,
                "retrieval_top": retrieval.top_score if retrieval else None,
                "message_chars": len(request.message),
                "latency_ms": latency_ms,
            },
        )
        yield ChatEvent("done", {})

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """The non-streaming form: the same events, collected."""
        parts: list[str] = []
        activities: list[ToolActivity] = []
        final: dict[str, object] = {}
        intent = "rag"
        async for event in self.stream(request):
            if event.event == "token":
                parts.append(str(event.data["text"]))
            elif event.event == "tool":
                activities.append(ToolActivity.model_validate(event.data))
            elif event.event == "route":
                intent = str(event.data["intent"])
            elif event.event == "final":
                final = event.data
        retrieval = final.get("retrieval")
        return ChatResponse(
            answer="".join(parts).strip(),
            intent=intent,  # type: ignore[arg-type]
            tools=activities,
            citations=[Citation.model_validate(c) for c in final.get("citations", [])],  # type: ignore[union-attr]
            retrieval=RetrievalMeta.model_validate(retrieval) if retrieval else None,
            disclaimer=str(final.get("disclaimer", DISCLAIMER)),
        )
