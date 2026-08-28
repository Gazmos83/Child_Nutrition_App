## Context

See proposal.md — Why. Constraints that shape the approach: `backend/tools/` and
`backend/nutrition/` must stay free of HTTP and database concerns (the audit emitters live
there and take only their validated input); `backend/chat/` is deliberately database-free;
existing tests read the audit lines with `record.getMessage().removeprefix("meal_plan_audit ")`
and assert on `caplog.text` for routing lines, so message *text* must not change shape;
prompts, corpus, and retrieval behaviour are frozen for the RAGAs baseline; no API
request/response model may change. Since `day-6-auth-and-persistence`, identity exists on
the server: `get_current_user` yields the `User`, and `owned_child` / `resolve_chat_request`
yield the `ChildProfile` a request is about.

## Goals / Non-Goals

**Goals:** every record correlatable to its request, account, and child without any
emitter knowing about HTTP; one line format; latency on requests, tools, and retrieval; one
error record per failure with an id the client can quote; a short, explicit list of what is
never logged.

**Non-Goals:** tracing, metrics, dashboards, log shipping/rotation, persisting audit to
PostgreSQL, logging free text (message, answer), any frontend change.

## Decisions

### 1. Stdlib `logging` with a JSON `Formatter` and a context `Filter`; no `structlog`

**Decision:** `backend/core/logging.py` provides `JsonFormatter(logging.Formatter)`,
`RequestContextFilter(logging.Filter)`, and `configure_logging(settings)`; nothing new is
installed.

**Why:** the need is one formatter, one filter, and three context variables. `structlog`
would add a dependency, a second logging API next to the nineteen modules already using
`logging.getLogger(__name__)`, and a processor pipeline to learn on the tightest day. The
stdlib formatter reads `record.__dict__` for extras, so `logger.info("…", extra={...})` and the
existing printf-style calls both serialise correctly. Every existing `caplog` test keeps
working because caplog captures `LogRecord`s before formatting.

**Alternative considered:** `structlog` with `structlog.stdlib` integration — good tooling, but
its value (bound loggers, processors) is not needed for six record types.

### 2. Correlation via `contextvars`, stamped by a filter — emitters stay ignorant

**Decision:** `backend/core/request_context.py` holds three `ContextVar`s (`request_id`,
`user_id`, `child_profile_id`) with `set_*`/`get_*` helpers and a `reset` for tests.
`RequestContextFilter` copies them onto every record. The middleware sets `request_id`;
`get_current_user` sets `user_id`; `owned_child` and `resolve_chat_request` set
`child_profile_id`. `generate_meal_plan`, `detect_nutrient_gaps`, `RagPipeline`, and
`ChatService` change nothing to become correlated.

**Why:** the audit emitters take a validated `MealPlanRequest`/`GapDetectionRequest` and must
not learn about accounts (that is what keeps `backend/tools` reusable and hard rule 6 easy to
audit). `contextvars` follow the task across `await`s and into the streaming generator, so
the `final`/`done` events and the routing summary emitted late in the stream still carry
the id. The correlation fields therefore ride as record *attributes*, not inside the audit
JSON message — which is exactly why the existing tests' `removeprefix("meal_plan_audit ")`
parsing is untouched. In the JSON format they appear as top-level keys next to `message`.

**Alternative considered:** pass `request_id`/`child_profile_id` down as tool arguments and
into the audit dict. Rejected: it changes `MealPlanRequest` (a tool schema the model binds
to) and threads HTTP identity through the pure layers.

### 3. A pure ASGI middleware, not `BaseHTTPMiddleware`

**Decision:** `backend/api/middleware.py::RequestContextMiddleware` is a plain ASGI callable:
on `http` scope it reads `X-Request-ID` (accepted only if it parses as a UUID; else a new
`uuid7()`), sets the contextvar, wraps `send` to add the header on `http.response.start` and
to note the status, and on completion emits the access record with `latency_ms` measured
from receipt to the final body message. Route path comes from `scope["route"].path` when
Starlette has matched one, else the raw path — so `/api/children/{child_id}` is logged
without the id in it.

**Why:** Starlette's `BaseHTTPMiddleware` runs the downstream app in a separate task, which
is precisely the case where `contextvars` set upstream become invisible downstream and where
streaming responses have historically misbehaved. A raw ASGI callable runs in-task, costs
~40 lines, and gives an accurate end-of-stream latency for SSE. `/health` is logged at
`DEBUG` by path match. The user id is read from the contextvar at completion, so it is present
whenever `get_current_user` ran, and null otherwise (401s included).

**Alternative considered:** `@app.middleware("http")` (which *is* `BaseHTTPMiddleware`).
Rejected for the reasons above; also a FastAPI dependency for the id — rejected because
dependencies do not see the response or its timing.

### 4. Logging is configured in `create_app()`, once, idempotently

**Decision:** `configure_logging(settings)` replaces the root logger's handlers with one
`StreamHandler(stdout)` carrying the chosen formatter and the context filter, sets the level
from `LOG_LEVEL`, and is called at the top of `create_app()`. Module-level `basicConfig` in
`backend/main.py` is removed. `LOG_FORMAT` defaults to `json`; `.env.example` sets `text` for
local reading. Uvicorn's own access logger is redundant with the middleware's record; the
README documents `--no-access-log`.

**Why:** configuration at import time cannot read settings without importing them at import
time, and cannot be re-run by tests. Replacing handlers (rather than adding) keeps repeated
`create_app()` calls in tests from duplicating output. `caplog` attaches its own handler to
the root logger, so this coexists with every existing test.

### 5. Tool and retrieval latency measured where the calls already are

**Decision:** `ChatService._run_one` wraps `tool.ainvoke` in `perf_counter` and emits one
`INFO` record on logger `backend.chat.tools` with `extra={"tool", "status", "latency_ms",
"used_context", "error_kind"}`; the routing summary gains `message_chars`. `RagPipeline.retrieve`
times `retriever.retrieve` and adds `latency_ms` and `queries` to the existing `rag` line as
`extra` fields (the printf text stays, so `caplog.text` assertions hold).

**Why:** both call sites already exist and already build the objects the records need
(`ToolActivity`, `RetrievalResult`); the queries are already returned to the client in
`RetrievalMeta`, so logging them exposes nothing new. No retrieval behaviour changes.

### 6. The middleware answers unhandled exceptions; request id in the 500 body and the SSE error event

**Decision:** `RequestContextMiddleware` catches any exception that escapes the router,
logs one `ERROR` record with `exc_info` on `backend.api.errors`, and — if no response has
started — sends `500 {"detail": <fixed copy>, "request_id": ...}` itself, with the
`X-Request-ID` header. `_event_stream` in `chat.py` and `ask.py` add `"request_id":
get_request_id()` to the terminal `error` event. `HTTPException`s are untouched (they are
deliberate responses handled inside the router, not failures).

**Why:** today a crash yields Starlette's default 500 with no record the parent could quote
and a `logger.exception` that cannot be tied to the request. The first draft of this decision
used `@app.exception_handler(Exception)`; at apply time that proved wrong: Starlette runs
those handlers in `ServerErrorMiddleware`, the *outermost* layer — outside this middleware,
after its request context is gone and past the point where the header can be added. Handling
the failure inside the middleware keeps the id, the header, and the access record (status 500)
in one place. The SSE `error` event already exists; adding a field is additive, and the
chat-ui reads `message` only, so nothing breaks. The 500 body mirrors FastAPI's
`{"detail": ...}` shape.

### 7. What is never logged — an explicit list, enforced by tests

**Decision:** passwords, hashes, session tokens, cookies, request headers, emails, and the
parent's message/answer text are never passed to a logger. The access record logs the route
template and status, no query string, no headers. The routing summary logs `message_chars`.
The doctor's note stays in the audit snapshot because hard rule 8 names it. A test signs in
and asserts none of the credential material appears in any captured record; a chat test
asserts the message text does not.

**Why:** the chat carries a child's health details; the log must be safe to hand to a
platform's log viewer. Hard rule 8 is a stated requirement to keep the note; the deliberate
audit sink (Decision 8) is how that record can be kept separately if retention rules differ.

**Found at apply time:** `backend/db/session.py` created the engine with
`echo=settings.app_env == "dev"`, and SQLAlchemy's echo prints bound parameters — the
live check showed the account's email and password hash in the main log on registration.
Echo is now off in every environment; `sqlalchemy.engine` can be raised to `DEBUG` locally
when a query needs inspecting. `tests/test_logging.py::TestEngineNeverEchoes` pins it.

### 8. Audit sink: optional file handler on `backend.tools.audit`

**Decision:** `AUDIT_LOG_PATH: str | None`. When set, `configure_logging` attaches a
`FileHandler` with the JSON formatter and the context filter to logger `backend.tools.audit`
and sets `propagate=False` so the record is not duplicated on stdout. When unset, propagation
stays on and audit records flow with the rest.

**Why:** hard rule 8 records may need longer retention than access logs; a separate file is
the smallest mechanism that allows it without a database table. Propagation is the only
knob needed to avoid double-writing.

### 9. Settings: three new optional fields on `Settings`

**Decision:** `log_format: Literal["json","text"] = "json"`, `log_level: str = "INFO"`
(validated against `logging.getLevelNamesMapping()`), `audit_log_path: str | None = None`.
Blank values read as absent, matching the Day 6 rule for `SESSION_SECRET`.

**Why:** `Settings` already requires `DATABASE_URL`, which `create_app()` tolerates being
absent (`/health` degrades). `configure_logging` therefore accepts a `Settings | None` and
falls back to defaults when settings cannot be built, so a misconfigured database never
disables logging.

## Risks / Trade-offs

- **`contextvars` and `TestClient`** → `TestClient` runs the app on its own loop/thread;
  contextvars set inside the app are visible to records emitted inside the app (same task),
  which is all that matters. Tests assert on captured records, not on the test thread's view.
- **Uvicorn duplicates the access line** → documented `--no-access-log`; not enforced in
  code because uvicorn owns its loggers.
- **Wrapping `send` in the middleware misses latency for responses that never start** → the
  middleware's own `except` emits the error record with the request id and sends the 500;
  the access record is emitted in a `finally`, with status 500.
- **The matched `Route.path` is relative to its own router** → with FastAPI's nested
  `_IncludedRouter`, `scope["route"].path` is `/foods`, not `/api/foods`. The template is
  rebuilt from the raw path by substituting `scope["path_params"]` values with `{name}`.
- **`extra=` keys colliding with `LogRecord` attributes (`name`, `message`, `args`)** →
  the formatter reads a fixed allowlist of context keys plus any key not in
  `logging.LogRecord.__dict__`'s reserved set; emitters use `tool`, `latency_ms`,
  `used_context`, `queries`, never reserved names. A unit test emits a record with each planned
  extra.
- **Existing `caplog.text` assertions** → message text is unchanged everywhere; new data is
  `extra`. `tests/test_chat_service.py::test_routing_log_line` is re-run explicitly.
- **JSON default surprises local readers** → `.env.example` sets `LOG_FORMAT=text`; README
  states the default.

## Migration Plan

1. Land settings, `request_context`, `logging`, middleware, exception handler (all additive).
2. Set `LOG_FORMAT=text` in `.env` for local work; leave `json` as the default for Day 7.
3. Run uvicorn with `--no-access-log`.
4. Rollback: `git revert` of the single commit; no data or schema involved.
