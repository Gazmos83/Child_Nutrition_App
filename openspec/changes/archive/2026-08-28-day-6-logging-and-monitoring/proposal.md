## Why

Reference §14 commits the MVP to application-level logging and monitoring — queries,
routing decisions, tool calls, retrieval results, errors, and latency — with structured logs
as the deliverable and no dashboard. Today the backend has `logging.basicConfig` with a
printf format, no request or correlation identifier anywhere, no identity in any line, and
latency measured only inside the chat service. The hard-rule-8 audit records
(`meal_plan_audit`, `nutrient_gaps_audit`) exist and are complete as snapshots, but nothing
ties one to the HTTP request, account, or stored child profile that produced it, so two
concurrent plans are indistinguishable in the stream and a support question ("what did the
app tell me on Tuesday?") cannot be answered from the logs. Errors are logged ad hoc with no
identifier a parent could quote back. Day 7 deploys this; a deployed service with unreadable
logs is not monitored.

**Scope: [MVP]. Day 6 of 7, second workstream — after `day-6-auth-and-persistence`
(merged), before the RAGAs A/B evaluation.** Time-box: half a day. Additive; developed on
`main`.

## What Changes

- **One log format** — a stdlib `logging.Formatter` subclass emitting one JSON object per
  record (`ts`, `level`, `logger`, `message`, `request_id`, `user_id`, `child_profile_id`,
  plus any structured extras), selected by `LOG_FORMAT=json|text` (default `json`), with
  `LOG_LEVEL` (default `INFO`). Configuration moves from module import time into
  `create_app()`.
- **Request correlation** — an ASGI middleware assigns every request a UUIDv7 request id (or
  honours a well-formed incoming `X-Request-ID`), returns it as `X-Request-ID`, and emits one
  access record per request: method, route path, status, `latency_ms`, and `user_id` when the
  request authenticated. `/health` access records are emitted at `DEBUG` so probes do not
  drown the log.
- **Correlation on every record, automatically** — `request_id`, `user_id`, and
  `child_profile_id` live in `contextvars`; a `logging.Filter` stamps them onto every record
  in the request. `get_current_user` sets the user id from the session; `owned_child` and the
  chat's `resolve_chat_request` set the child id from the stored profile they resolved. The
  existing `meal_plan_audit`, `nutrient_gaps_audit`, `rag`, and `chat` lines therefore become
  correlatable without touching `backend/tools/` or `backend/nutrition/`.
- **Tool-call records** — one structured record per tool invocation (`tool`, `status`,
  `latency_ms`, `used_context`) from the chat service's existing execution loop.
- **Retrieval latency** — the existing `rag` summary line gains `latency_ms` and the queries
  issued (already returned to the client in `RetrievalMeta`).
- **Unhandled errors** — one structured `ERROR` record with the traceback and request id; the
  client receives a 500 body `{"detail": <fixed message>, "request_id": ...}` and never a
  traceback. Streaming `error` events on `/api/chat` and `/api/ask` gain a `request_id` field
  (additive).
- **Deliberate audit sink** — `AUDIT_LOG_PATH` (optional) sends the `backend.tools.audit`
  logger to its own JSON-lines file instead of the shared stream, for retention independent
  of stdout.
- **What is never logged** — passwords, password hashes, session tokens, cookies, request
  headers, email addresses, and the parent's raw chat message (only its length). The doctor's
  note stays in the audit snapshot because hard rule 8 requires it.

## Capabilities

### New Capabilities

- `observability`: the shape and content of the application's logs — one structured record
  format, per-request correlation and identity, an access record with latency per request,
  tool-invocation and retrieval records, a single structured error record with a client-quotable
  request id, a deliberate audit sink, and the list of what is never written to a log.

### Modified Capabilities

- `meal-plan-generation`: *Every meal-plan generation is logged with its full input snapshot*
  — the record is additionally correlated to the request, account, and stored child profile
  when the plan was produced through the chat.
- `nutrient-gap-detection`: *Every gap detection is logged for audit* — same correlation.
- `intent-routing`: *Every routing decision is logged* — the record carries the request id,
  and one record per tool invocation with its latency and outcome accompanies it.
- `chat-api`: responses carry `X-Request-ID`; a failure after streaming began and a 500 both
  carry the request id.
- `ask-api`: same as `chat-api`.

## Impact

- **New code**: `backend/core/request_context.py` (contextvars + setters),
  `backend/core/logging.py` (JSON formatter, context filter, `configure_logging`),
  `backend/api/middleware.py` (request id + access record), `tests/test_logging.py`,
  `tests/test_api_request_id.py`.
- **Touched code**: `backend/main.py` (configure logging and register the middleware and the
  unhandled-exception handler in `create_app`; drop module-level `basicConfig`),
  `backend/core/config.py` (`log_format`, `log_level`, `audit_log_path`), `backend/api/deps.py`
  (set `user_id` / `child_profile_id` in context), `backend/api/chat.py` (set child id in
  `resolve_chat_request`; `request_id` on the SSE `error` event), `backend/api/ask.py`
  (`request_id` on the SSE `error` event), `backend/chat/service.py` (per-tool timing and
  record; message length instead of nothing), `backend/rag/pipeline.py` (`latency_ms`,
  `queries` on the existing line), `.env.example`, `README.md`.
- **Untouched**: `backend/tools/`, `backend/nutrition/`, prompts, corpus, retrieval behaviour
  (frozen for the RAGAs baseline), the frontend, every request/response model. Existing
  `caplog`-based tests keep passing: audit message text is unchanged (`meal_plan_audit <json>`);
  correlation arrives as record attributes, not inside the message.
- **API surface**: additive only — one response header on every route, one field on the 500
  body, one field on the streaming `error` event.
- **Dependencies**: none. Stdlib `logging`, `contextvars`, `uuid`, `time`.
- **Operations**: run uvicorn with `--no-access-log` so the middleware's record is the single
  access line. Hard rule 8 audit content is unchanged; it gains correlation.

## Non-goals

- **LangSmith tracing, token/cost dashboards, metrics endpoints (`/metrics`), OpenTelemetry**
  — [Stretch] per §14; a structured log is the MVP deliverable.
- **A `structlog` dependency** — the stdlib covers a formatter, a filter, and three
  contextvars; see design.md Decision 1.
- **Persisting audit records to PostgreSQL** — the audit is a log record by design (hard rule
  8 says "log"); a table is a Day 7+ decision if retention needs it.
- **Logging the parent's message text or the model's answer** — health-adjacent free text; the
  routing decision, retrieval queries, and tool records are what §14 asks for.
- **Log rotation, shipping, and retention** — the deployment platform's concern on Day 7.
- **Showing the request id in the UI** — the SSE `error` event carries it; rendering it is a
  Day 7 polish item.
