## Why

Days 1–4 built every component and connected none of them. `POST /api/ask` answers only
from the knowledge base; the six deterministic tools exist as typed LangChain tools that
nothing calls; there is no user interface at all. A parent cannot yet ask "how much protein
does *my* baby need?" and get a number, because no code decides that this question needs a
tool rather than a passage. Day 5 adds that decision point — a lightweight intent router —
and the production chat UI that shows the parent the answer, where it came from, and which
tools produced it.

**Scope: [MVP]. Day 5 of 7.** This is the first of two Day 5 changes; the second
(`day-5-feeding-log-and-gaps`) adds the feeding-log and nutrient-gap tools from reference
§9b on top of the router and UI built here.

## What Changes

- **Intent routing** — a single language-model call, with the Day 4 tools and a
  "search the guidelines" capability bound as callable tools, decides whether a message is
  answered from the knowledge base (`rag`), from deterministic tools (`tool`), or both
  (`hybrid`). The model's chosen calls *are* the routing decision; execution is then
  deterministic Python. The model's own free text is never returned as an answer: every
  reply is composed from retrieved context blocks and/or validated tool results. At most
  four tool calls per turn, one routing round, no agent loop (architecture principle: no
  LangGraph in MVP).
- **Child context in the request, not in the database** — the UI collects the child's
  details (age in months, weight, sex, optional height, diet preference, allergies,
  doctor's note, activity level) in a form and sends them with every message. The backend
  treats these values as authoritative: any profile-backed argument the model proposes for
  a tool is replaced by the request's value, and the tool-activity record says so. The
  model never invents a weight or an age. No profile is read or written server-side, so no
  user-scoped route exists and hard rule 9 holds by construction; Day 6 replaces the
  payload with auth-scoped `ChildProfile` rows behind the same seam.
- **`POST /api/chat`** — a new streaming endpoint alongside the untouched `/api/ask`.
  Server-sent events carry, in order: the routing decision, each tool's activity (name,
  validated arguments, which arguments came from the child context, result or error), the
  answer tokens, the final citations/disclaimer, and completion. A non-streaming JSON form
  returns the same content. Bounded client-held conversation history (≤ 12 turns) lets the
  router resolve follow-ups ("and iron?"); nothing is persisted.
- **Tool failures are surfaced, never hidden** — a validation error (e.g. BMI requested
  with no height), an unknown food, or a safety violation becomes an error entry in the
  tool activity and is explained in the answer; the stream still completes.
- **Every routing decision is logged** (intent, planned and executed tools with status,
  retrieval statistics, latency) so Day 6's logging/monitoring extends a record that
  already exists.
- **Next.js production UI** (`frontend/`) — one screen: a chat pane and a side panel with
  the child-context form. Each assistant message shows an intent chip, tool-activity chips
  (expandable to arguments and results), a structured **meal-plan card** when
  `generate_meal_plan` ran (items by meal slot, coverage against targets, exclusions with
  reasons, an unmissable banner when a doctor's note overrode a target — hard rule 3),
  the answer with inline `[n]` citation markers, a numbered **Sources** list with source
  and publication year (hard rule 5), and the not-medical-advice disclaimer on every
  message. Backend access goes through Next.js rewrites so the browser talks to one origin.
- **One voice, written once** — every message the product itself writes to a parent
  (empty states, the no-safe-plan headline, the doctor's-note banner, missing-details hints,
  tool failures, interrupted or unreachable states) lives in one copy module per side and
  follows a single tone: warm, unhurried, a little playful about everyday feeding; warm and
  direct — no wordplay — the moment safety, allergies, a doctor's instruction, or an error
  is involved. The Day 4 no-safe-plan text is re-voiced to match. The Day 3 RAG prompt and
  disclaimer are frozen for Day 6's evaluation and are not touched.
- **Small refactors with no behaviour change** — the RAG pipeline's retrieval step becomes
  public so hybrid answers can reuse retrieval without generation; the SSE frame helper
  moves to a shared module; the test fake chat model learns to script tool calls.

## Capabilities

### New Capabilities

- `intent-routing`: deciding, per message, whether to answer from the knowledge base,
  from deterministic tools, or both; binding request-supplied child context to tool
  arguments; bounding tool calls; surfacing tool failures; logging the decision.
- `chat-api`: the `POST /api/chat` contract — request validation (message, child
  context, history), the ordered server-sent-event stream, the non-streaming JSON form,
  and error/unavailability behaviour.
- `chat-ui`: the browser application — child-context form, streamed chat, citation
  display, tool-activity display, meal-plan card with override conflict banner, disclaimer
  on every assistant message, and degraded states (no child context, backend unavailable,
  interrupted stream).

### Modified Capabilities

None. `rag-answering`, `advanced-rag-retrieval`, and `ask-api` keep their requirements
unchanged: the `rag` path of the new endpoint delegates to the existing pipeline, and
`/api/ask` is untouched so Day 6's A/B evaluation measures exactly what Day 3 built.
`deterministic-nutrient-tools` and `meal-plan-generation` are called, not changed.

## Impact

- **New code**: `backend/chat/` (prompts, router, service, wiring), `backend/schemas/chat.py`,
  `backend/api/chat.py`, `backend/api/sse.py`; the whole `frontend/` application; root
  `pnpm-workspace.yaml`.
- **Touched code**: `backend/api/router.py` (mounts the new route; still no user-scoped
  routes), `backend/api/ask.py` (imports the moved SSE helper), `backend/rag/pipeline.py`
  (retrieval step made public, behaviour identical), `backend/tools/meal_plan.py` (the
  `NO_SAFE_PLAN_MESSAGE` text only; its test imports the constant), `tests/fixtures/fake_llm.py`
  (scripted tool calls, `bind_tools`), `README.md`, `.gitignore`.
- **API surface**: adds `POST /api/chat`. `/api/ask` and `/health` unchanged.
- **Dependencies**: no new Python packages — `langchain-openai` already provides tool
  binding, and OpenRouter's OpenAI-compatible endpoint supports function calling for the
  configured model. Frontend introduces its own `pnpm` dependency tree (Next.js, React,
  Tailwind, shadcn/ui, TanStack Query, Vitest).
- **Cost**: one extra model call per message (routing) before the answer call; both use
  the already-configured OpenRouter model at temperature 0.
- **Data / security**: no database access, no identity, nothing persisted. Child context
  and history live in the browser and travel in the request body. Every request, tool
  argument, and model-proposed argument is Pydantic-validated (hard rule 7).

## Non-goals

- **Authentication, saved child profiles, persisted conversations** — Day 6, together
  with Day 1's outstanding database tasks. The request-payload seam is designed to be
  replaced by auth-scoped reads without changing the router.
- **Feeding log, nutrient-gap detection, daily plan adjustment (reference §9b)** — the
  second Day 5 change, `day-5-feeding-log-and-gaps`, which builds on this endpoint and UI.
- **AI-safety boundary layer** (diagnosis, emergency, medication, extreme-dieting
  refusals) — Day 6. Today an out-of-domain message falls into the relevance floor and
  receives the existing no-answer message.
- **Full LangGraph agent, multi-round tool loops, LangSmith tracing** — [Stretch], only if
  Days 6–7 finish early.
- **Strategy (basic/advanced) toggle in the UI, dark-mode polish, i18n, a separate
  meal-planner page** — not MVP. Meal plans are requested and shown in chat.
- **CORS configuration** — avoided by same-origin rewrites; added only if streaming through
  the Next.js dev proxy proves unworkable (design.md records the fallback).
