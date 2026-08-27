## Context

See proposal.md — Why. The pieces exist and are tested in isolation:

- `backend/rag/pipeline.py` — `RagPipeline.answer()`/`stream()` with a fixed system prompt,
  relevance floor judged on the original question, code-attached `DISCLAIMER`, and a
  private `_prepare()` that does retrieval + context construction.
- `backend/tools/langchain_tools.py` — `build_tools(chat_model)` returns six `StructuredTool`s
  whose `args_schema` is the Pydantic input model, so model-proposed arguments are validated
  before the function runs. Five are sync; `generate_meal_plan` is coroutine-only.
- `backend/api/ask.py` — hand-formatted SSE over `StreamingResponse`, a `get_rag_pipeline`
  dependency that maps `RuntimeError` to 503, and `tests/test_api_ask.py` showing the
  test pattern (`dependency_overrides`, `RecordingChatModel`, `InMemoryKnowledgeStore`).
- `backend/api/router.py` — mounts only routes that are not user-scoped, by design, until
  auth ships on Day 6.
- `tests/fixtures/fake_llm.py` — `RecordingChatModel` scripts string replies and streams
  word-by-word; it has no `bind_tools` and cannot emit tool calls.

Constraints shaping the design: no database or auth today (Day 1 §7 open, `DATABASE_URL`
is a placeholder); no LangGraph; the LLM never produces nutrient numbers; `/api/ask` must
stay byte-identical for Day 6's A/B evaluation; `langchain-core`/`langchain-openai` 1.6.0
with `ChatOpenAI.bind_tools` available; Node 24 + pnpm 11 installed; no frontend exists.

## Goals / Non-Goals

**Goals:**
- One seam between "what the parent typed" and "what runs": a routing decision that is a
  list of validated tool invocations, executed by plain Python.
- Child context flows from the request into tool arguments deterministically, and the
  place it is resolved is the single place Day 6 swaps in database-backed profiles.
- The `rag` path is *the* Day 3 pipeline, not a copy.
- The UI renders provenance (citations, tool activity, override conflicts) as first-class
  content, not as a debug panel.

**Non-Goals:**
- Multi-round tool loops, planning, or self-correction by the model.
- Any persistence or identity. Any change to `/api/ask` behaviour.
- A frontend design system beyond shadcn defaults; visual polish is Day 7.

## Decisions

### 1. Routing = one `bind_tools` call; the returned `tool_calls` are the decision

**Decision:** Build the routing model as `chat_model.bind_tools(nutrient_tools +
[search_guidelines])`, where `search_guidelines(query: str)` is a pseudo-tool standing
for the knowledge-base path. Invoke once with a routing system prompt, the formatted child
context, bounded history, and the message. Map the reply deterministically: only
`search_guidelines` → `rag`; only nutrient tools → `tool`; both → `hybrid`; none → `rag`
with `query = message`. Free text in the routing reply is discarded. `MAX_TOOL_CALLS = 4`;
extras are dropped and logged.

**Why:** Native function calling gives argument extraction against the tools' own Pydantic
schemas for free, so "route" and "extract arguments" are one call and one validation
path. Making retrieval a pseudo-tool lets the model write a standalone query (pronouns
resolved from history) — the only channel through which history influences retrieval,
which keeps `/api/ask` untouched. Deriving the intent from the call list, rather than
asking the model to name an intent, removes a class of inconsistency (model says "tool"
but proposes no call).

**Alternatives considered:** (a) a separate classifier call returning `{intent}` then a
second extraction call — two calls, two prompts, same information. (b) Letting the model
answer directly when it proposes no calls — rejected: an ungrounded answer with no
citations violates the spirit of hard rule 5; the relevance-floor fallback gives the
existing honest no-answer message instead.

### 2. `resolve_context()` is the authority seam for profile-backed arguments

**Decision:** `backend/chat/router.py:resolve_context(tool_name, model_args, request)`
returns the arguments actually used. For every field in `PROFILE_FIELDS = {age_months,
weight_kg, sex, height_cm, allergies, diet_preference, doctors_note, activity_level}`
that the target tool's `args_schema` declares and `request.child` supplies, the request
value replaces whatever the model proposed; the replaced/filled names are returned as
`used_context`. A mismatch between model and context is logged at INFO. If `request.child`
is `None`, model arguments pass through to Pydantic validation unchanged and a missing
required field surfaces as a validation error whose user-facing hint is ""Your little 
one's details go in the side panel — then we're good to go"".

**Why:** The parent's form is the truth; the model's job is to notice *which* tool, not to
re-transcribe a weight it saw in the prompt (and possibly round it). Concentrating this in
one function means Day 6 replaces "read `request.child`" with "load the authenticated
user's profile" and nothing else in the router changes. Recording `used_context` gives the
UI its "from your child's profile" label and gives Day 6's audit the provenance of every
argument.

**Alternative considered:** Omit profile fields from the tool schemas the model sees and
inject them after. Rejected — the tools' `args_schema` *is* the validation contract
(Day 4 Decision 10); forking a second schema per tool would drift.

### 3. Answer composition by path; the `rag` path is delegation, not reimplementation

**Decision:** `ChatService` executes the decision then composes:
- `rag` → `async for item in pipeline.stream(query, strategy)` — tokens and the final
  `RagResponse` are forwarded as `token`/`final` events. Prompt, floor, disclaimer, tone:
  Day 3's, untouched.
- `tool` / `hybrid` → retrieval (if any) via the newly public `pipeline.retrieve(query,
  strategy)`; then one streaming call with `ANSWER_WITH_TOOLS_SYSTEM_PROMPT` (the Day 3
  `SYSTEM_PROMPT` grounding rules plus: "state every number exactly as the tool result
  gives it; never recompute or convert; cite context blocks with [n]; if a tool failed, say
  what could not be computed and why; if `override.conflict` is true, say the doctor's note
  takes priority and give both values; do not add a disclaimer"), and the Day 5 voice
  (Decision 13): "write like a warm, unhurried friend who happens to know the guidelines —
  relaxed and a little playful about everyday feeding, plain and direct the moment safety,
  allergies, or a doctor's instruction is involved; never jokey about those; never scold".
  Tool results are appended as labelled JSON blocks after the context blocks. `DISCLAIMER`
  is attached by code.

**Why:** Delegating `rag` guarantees the A/B eval surface is identical. Tool answers need a
different instruction set (numbers verbatim, failures explained), so a second prompt is
honest rather than a mode flag in the first. Serialising results as JSON — not prose — is
what lets a test assert the model's numbers were passed through untouched.

### 4. `RagPipeline._prepare()` becomes public `retrieve()`; nothing else moves

**Decision:** Rename `_prepare` → `retrieve` and `_Prepared` → `RetrievedContext`
(exported). `answer()` and `stream()` call `retrieve()`; behaviour, logging, and the
floor logic are unchanged line for line.

**Why:** Hybrid needs context blocks and citations without generation. A rename is the
smallest change that provides it; a wrapper class or a second retrieval helper would
duplicate the floor logic.

### 5. Tool execution: `StructuredTool.ainvoke`, errors become activity records

**Decision:** Each accepted call runs `await tool.ainvoke(resolved_args)` (sync tools run
in LangChain's default executor). `pydantic.ValidationError`, `FoodNotFoundError`, and
`UnsafePlanError` are caught per invocation and become `ToolActivity(status="error",
error=<parent-facing message>, detail=<first technical error>)`; any other exception is
also caught per invocation, logged with `exception`, and reported as a generic failure.
The parent-facing `error` text comes from `backend/chat/copy.py` (Decision 13): no child
details supplied → `MISSING_CHILD_INFO_HINT` (the Decision 2 hint); a specific missing
argument such as height → `missing_field_hint(field)` ("We need your child's height for
this one — pop it in the side panel and we'll take it from there"); an unknown food →
`unknown_food(food_id)` ("We don't know a food called “{id}” yet — try picking one from
the list"); `UnsafePlanError` → `SAFETY_STOP` ("We stopped this plan because a safety
check didn't pass. That's on us, not you — nothing unsafe was shown. Please try once
more"); anything else → `TOOL_FAILED` ("That one didn't work out on our side. Everything
else in this answer still stands"). The answer step receives failed activities too, so the
model can explain them in the same voice. Nothing here can abort the stream.

**Why:** One failed tool must not cost the parent the whole answer (spec: surfaced, not
swallowed). Catching per invocation rather than around the batch keeps successful results.

### 6. `POST /api/chat` event contract and JSON form

**Decision:** Events, via `sse()` moved to `backend/api/sse.py`:

```
route   {"intent", "planned": [tool names]}
tool    {"name", "status", "args", "used_context", "result"|null, "error"|null}   (per invocation)
token   {"text"}
final   {"citations", "retrieval"|null, "disclaimer", "intent", "tools": [{"name","status"}]}
done    {}          |   error {"message"}
```

`tool` events are emitted after execution and before the answer call starts, so the UI
shows activity while the model writes. The `error` event's `message` is
`STREAM_FAILED` from `backend/chat/copy.py` — "We lost the thread mid-answer. Please try
again — your child's details are safe in the side panel" — never an exception string.
`stream=false` returns `ChatResponse{answer, intent, tools, citations, retrieval,
disclaimer}`. 503 mapping and `Cache-Control` /
`X-Accel-Buffering` headers copy `ask.py`. `get_chat_service()` is an `lru_cache`
builder mirroring `backend/rag/llm.py:get_pipeline()` and is the dependency tests override.

**Why:** Typed events let the frontend reducer be a pure function with a test per event.
Emitting tool activity before tokens is what makes "tools used" feel live. Reusing the
`ask.py` patterns keeps the two endpoints consistent for Day 6 hardening.

### 7. Request model: `extra="forbid"`, bounded everywhere

**Decision:** `ChatRequest{message (1–2000, stripped), child: ChildContext|None,
history: list[ChatTurn] ≤ 12 (role ∈ user|assistant, content ≤ 2000), strategy, stream}`.
`ChildContext` mirrors `MealPlanRequest`'s fields and reuses `_AGE/_WEIGHT/_HEIGHT` from
`backend/schemas/tools.py` (ages in months, enums for allergies/diet, height ≤ 150 cm).

**Why:** Same posture as `AskRequest` — a misspelt field is an error, not silence. Sharing
the field definitions with the tool schemas means the form cannot accept what a tool
would reject.

### 8. Test fake: scripted tool calls, backward compatible

**Decision:** `RecordingChatModel.responses` accepts `str | AIMessage`; a string behaves
as today, an `AIMessage` (with `tool_calls`) is returned as-is. `bind_tools(tools, **kw)`
returns `self` and appends the tool names to `self.bound_tools`. Streaming of an
`AIMessage` response yields its text content word by word as before.

**Why:** All 466 existing tests keep passing with no edits; router tests script a
`ToolCall` list in one line.

### 9. Frontend: Next.js App Router, shadcn/ui, TanStack Query, Vitest; rewrites not CORS

**Decision:** `pnpm create next-app frontend` (TypeScript, Tailwind, App Router,
`src/`), shadcn/ui for primitives, `@tanstack/react-query` for the send mutation,
Vitest for unit tests. `next.config.ts` rewrites `/api/:path*` to
`${BACKEND_URL}/api/:path*` (server-side env, default `http://localhost:8000`). Root
`pnpm-workspace.yaml` lists `frontend`.

**Why:** Rewrites make the app same-origin in dev and prod — no CORS surface, no
browser-visible backend URL, one deployable pair on Day 7. TanStack Query is the mandated
stack; a `useMutation` whose `mutationFn` drives the stream reader is the smallest fit.

**Fallback recorded:** if the dev proxy buffers SSE so tokens arrive in a burst, add
`CORSMiddleware` to `backend/main.py` with a `CORS_ORIGINS` setting and call the backend
directly. Decide by observing the stream during apply, not by speculation.

### 10. Streaming client is a pure parser + pure reducer

**Decision:** `src/lib/sse.ts:parseSseFrames(chunk, carry) → {events, carry}` handles
frames split across chunks. `src/lib/chat-reducer.ts` maps each event onto an
`AssistantMessage` state (`intent`, `tools[]`, `text`, `citations`, `retrieval`,
`disclaimer`, `status: streaming|done|error|interrupted`). The hook `use-chat.ts` owns the
`fetch` + `ReadableStream` loop and dispatches to the reducer; on a thrown read error it
marks the message `interrupted`, keeping received text.

**Why:** The parser and reducer are the only non-trivial frontend logic; keeping them pure
makes them the unit-test surface (spec: interrupted stream keeps partial text).

### 11. Provenance is content: message anatomy and the meal-plan card

**Decision:** `AssistantMessage` renders, top to bottom: intent chip → tool-activity chips
(`✓`/`✗`, name, collapsible args/result JSON, "from your child's profile" badge from
`used_context`) → `MealPlanCard` when a `generate_meal_plan` result is present → answer
text with `[n]` as superscript anchors → `Citations` (`[n] Source (Year) — topic,
section`, collapsible excerpt) → `Disclaimer`. `MealPlanCard`: items grouped by `meal`
slot with `servings × serving_size serving_unit`; three coverage bars from `coverage`;
`exclusions` list with reasons; an amber banner when `override.conflict` is true titled
"Your doctor's note takes priority here" with the line "We're using {applied_value}
{unit} instead of the usual {general_value} {unit} for {nutrient}, just as your doctor
asked"; `no_safe_plan` renders the result's `message` as the headline — "We couldn't build
a safe plan with these details — here's why, and what you might want to check" — followed
by two sections: **Here's why** (the `exclusions` list with reasons) and **Worth checking**
(a fixed checklist: age in months, recorded allergies, diet preference, and "your
pediatrician can suggest foods that fit"). The card is rendered from the `tool` event's
`result` — the model's prose is never parsed for numbers.

**Why:** Hard rules 3 and 5 are UI requirements as much as backend ones; rendering them
from structured results, not from the answer text, means the model cannot un-flag a
conflict or drop a citation by phrasing.

### 12. Child context lives in the browser, typed against the backend vocabularies

**Decision:** `ChildContextForm` state is a `ChildContext` object mirroring the backend
schema; enum options come from `src/lib/enums.ts`, with a Vitest snapshot test comparing
them to a JSON fixture copied from `backend/models/enums.py` + `ActivityLevel` (the fixture
is regenerated by a one-line `uv run python -c` documented in the test). State is mirrored
to `localStorage` under one key inside try/catch and hydrated on mount; absence is a
valid state (the panel shows a "Tell us about your growing gourmet to get started" banner).

**Why:** The form must be unable to send what the backend rejects (hard rule 2). A
snapshot test is the cheapest drift alarm without a codegen step on day one.

### 13. Voice: one copy module per side, warm and playful by default, direct about safety

**Decision:** Every parent-facing string the product itself writes (as opposed to text the
model generates) lives in exactly one module per side — `backend/chat/copy.py` for
server-originated messages (tool-failure hints, the stream error, the no-safe-plan
headline) and `frontend/src/lib/copy.ts` for UI copy (empty states, banners, degraded
states, form hints). Components and services import from these; no literal parent-facing
string appears elsewhere. The tone guide, applied to every string:

- **Audience:** parents who want to feel relaxed and enjoy feeding their child. Default
  voice is warm, unhurried, a little playful ("growing gourmet", "we're good to go").
- **Safety, allergies, doctor's instructions, and errors are direct.** Warm, but no
  wordplay: say what happened, what it means, and what to do next, in that order. Never
  blame the parent; never minimise a safety stop.
- Speak as "we"; address the parent as "you" and the child as "your little one" or by
  role, never by assumed name or pronoun.
- One idea per sentence, no exclamation marks, no jargon without a gloss.
- Every empty or error state ends with the next step.
- Key names are read by people too (tool activity, logs, code review): name the *missing
  information*, never the child — `MISSING_CHILD_INFO_HINT`, not "missing child".

The strings this change ships (change 2 adds the feeding-log and gap-card set):

| Key | Copy |
|---|---|
| `PANEL_EMPTY` (side panel banner) | Tell us about your growing gourmet to get started |
| `CHAT_EMPTY` | Ask us anything about feeding your little one — what to start with, how much, or what a good day of meals looks like |
| `MISSING_CHILD_INFO_HINT` (backend; the Decision 2 hint) | Your little one's details go in the side panel — then we're good to go |
| `missing_field_hint(field)` (backend) | We need your child's {field} for this one — pop it in the side panel and we'll take it from there |
| `unknown_food(id)` (backend) | We don't know a food called “{id}” yet — try picking one from the list |
| `SAFETY_STOP` (backend) | We stopped this plan because a safety check didn't pass. That's on us, not you — nothing unsafe was shown. Please try once more |
| `TOOL_FAILED` (backend) | That one didn't work out on our side. Everything else in this answer still stands |
| `STREAM_FAILED` (backend `error` event) | We lost the thread mid-answer. Please try again — your child's details are safe in the side panel |
| `NO_SAFE_PLAN_MESSAGE` (backend, `backend/tools/meal_plan.py`) | We couldn't build a safe plan with these details — here's why, and what you might want to check |
| `OVERRIDE_TITLE` | Your doctor's note takes priority here |
| `overrideBody(nutrient, applied, general, unit)` | We're using {applied} {unit} instead of the usual {general} {unit} for {nutrient}, just as your doctor asked |
| `NO_SAFE_PLAN_WHY` / `NO_SAFE_PLAN_CHECK` (section titles) | Here's why · Worth checking |
| `NO_SAFE_PLAN_CHECKLIST` | Age in months · Recorded allergies · Diet preference · Your pediatrician can suggest foods that fit |
| `INTERRUPTED` | The connection dropped partway through. What arrived is above — tap retry and we'll finish the thought |
| `UNREACHABLE` (request failed before any event) | We couldn't reach the chef. Check your connection and try again |
| `UNAVAILABLE(detail)` (503) | We're not quite set up yet. {detail} |
| `TOOL_CHIP_FAILED` (chip label prefix) | Didn't work out |
| `FROM_PROFILE` (badge) | from your child's details |
| `FORM_AGE_HINT` | Age is in months — 0 to 60 — because the first year moves fast |
| `FORM_HEIGHT_HINT` | From 36 months we need height too; it's part of the calorie sums |
| `FORM_NOTE_HINT` | Anything your doctor wrote about calories, protein, or iron — we'll follow it |

**What stays as it is:** the Day 3 RAG `SYSTEM_PROMPT`, `DISCLAIMER`, and
`NO_ANSWER_MESSAGE` are frozen for Day 6's A/B evaluation and are not re-voiced here (see
Open Questions). The `DISCLAIMER` is rendered verbatim beneath the card copy.

**Why:** Tone is a product requirement, and a requirement scattered across forty
components cannot be reviewed. One table per side means the strings above *are* the
review surface, a Vitest snapshot keeps them from drifting, and the no-safe-plan and
override texts — the two moments a parent is most likely to feel judged or alarmed — are
written once, deliberately.

**Alternative considered:** letting the model phrase these states. Rejected — the model's
prose is never the source of safety-critical or structural text (Decision 11), and a
warm tone that varies per generation is not a tone.

## Risks / Trade-offs

- [Playful copy lands wrong next to a safety stop or an allergy exclusion] → the tone guide
  splits the voice explicitly: playful only for everyday states; safety/error strings are
  warm and direct with no wordplay. The copy table is the review artefact for exactly this.

- [The configured OpenRouter model returns malformed or no `tool_calls`] → Decision 1's
  fallback routes to `rag` on the raw message; the routing log records `planned=[]`, so
  the failure is visible in Day 6 monitoring rather than silent. Model choice remains a
  setting.
- [A model call per message doubles latency] → routing uses the same temperature-0 model
  with a short prompt; `tool` events stream immediately after routing so the UI is not
  idle. If routing latency dominates, a cheaper `OPENROUTER_ROUTER_MODEL` setting is a
  one-line follow-up, not a redesign.
- [Model proposes a tool for a hypothetical child ("what about a 3-year-old?") and the
  authoritative context overwrites it] → accepted for MVP; the `used_context` label makes
  the substitution visible. Day 6 can add an explicit "for a different child" path if
  evaluation shows demand.
- [Next.js rewrite buffers SSE in dev] → Decision 9's recorded fallback (CORS + direct
  calls), decided by observation during apply.
- [`generate_meal_plan` depends on the chat model for doctor's-note extraction and is
  slow] → it already is (Day 4); the `tool` event for it is emitted as soon as it returns,
  and the router runs tool invocations concurrently with `asyncio.gather` where more than
  one is planned.
- [Frontend scaffolding burns the morning] → scaffold with generators (`create-next-app`,
  `shadcn add`), no custom build config, no design system work; UI tasks are ordered so a
  plain-text chat works before cards and chips.
- [History injection lets a user steer the router with fabricated assistant turns] →
  history is untrusted input like the message; it influences *which* validated tool runs,
  never the numbers (context and tools do), and out-of-domain steering ends at the
  relevance floor. Day 6's safety layer sits on top of this.

## Migration Plan

1. Backend: land schemas → chat package → endpoint → tests; `uv run pytest -q` green with
   `/api/ask` tests untouched.
2. Frontend: scaffold → plain chat over `/api/chat` → child form → chips/citations → cards;
   `pnpm -C frontend build` green.
3. Verify end-to-end against a live OpenRouter key and the existing `milvus.db`.

**Rollback:** remove the `chat_router` include from `api_router` and delete `frontend/`;
`/api/ask` and every Day 1–4 module are unaffected. The `retrieve()` rename is
behaviour-neutral and can stay.

## Open Questions

- Whether `openai/gpt-4o-mini` routes well enough on tool selection, or a different
  OpenRouter model should be the routing default. Safely answerable during Day 6
  evaluation; it is a setting, not a design change.
- Whether to re-voice the Day 3 RAG `SYSTEM_PROMPT` and `NO_ANSWER_MESSAGE` in the Day 5
  voice. Deferred because Day 3's tone was frozen for the A/B evaluation; changing it
  affects both strategies equally, so it is a Day 6 decision to take with the eval in hand,
  not a Day 5 one.
