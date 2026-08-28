Additive change on `main`. Time-box: half a day. No request/response model changes; no
change to `backend/tools/`, `backend/nutrition/`, prompts, corpus, or retrieval behaviour.
Authorization boundary for every task that records identity: `user_id` comes only from
`get_current_user` (the session) and `child_profile_id` only from `owned_child` /
`resolve_chat_request` (the account's own row); nothing is read from a request body, and
identifiers — never emails — are logged.

## 1. Settings and context

- [x] 1.1 Add `log_format` (`json|text`, default `json`), `log_level` (validated against
  `logging.getLevelNamesMapping()`, default `INFO`), and `audit_log_path` (optional) to
  `Settings` in `backend/core/config.py`, blank values reading as absent; document them in
  `.env.example` (`LOG_FORMAT=text` for local work); verify `tests/test_config.py` covers the
  defaults, a rejected level name, and blank-as-absent
- [x] 1.2 Create `backend/core/request_context.py`: `ContextVar`s for `request_id`, `user_id`,
  `child_profile_id` with `get_*`/`set_*` helpers and `reset_request_context()`; verify a unit
  test in `tests/test_logging.py` shows values set inside a task are visible to a coroutine it
  awaits and absent outside

## 2. Formatter, filter, configuration

- [x] 2.1 Create `backend/core/logging.py`: `RequestContextFilter` (stamps the three context
  fields on every record), `JsonFormatter` (one object per line with `ts`, `level`, `logger`,
  `message`, the three context fields, `exc_info` text when present, and every non-reserved
  `extra` key), `TEXT_FORMAT` including `request_id`, and `configure_logging(settings | None)`
  that replaces the root handlers with one stdout handler at the configured level and, when
  `audit_log_path` is set, attaches a JSON file handler to `backend.tools.audit` with
  `propagate=False`; verify `tests/test_logging.py` parses an emitted JSON line, sees the
  context fields, sees an `extra` field, sees a traceback string for an exception record,
  sees `WARNING` suppress `INFO`, and sees the audit record land in a temp file exactly once
- [x] 2.2 Call `configure_logging` at the top of `create_app()` and remove the module-level
  `logging.basicConfig` from `backend/main.py`; verify `uv run pytest -q` stays green
  (`caplog` tests unaffected) and `tests/test_app.py` confirms `create_app()` twice leaves one
  root handler

## 3. Request correlation and access records

- [x] 3.1 Create `backend/api/middleware.py::RequestContextMiddleware` (pure ASGI): honour a
  UUID-shaped incoming `X-Request-ID` else `uuid7()`, set the contextvar, add the header on
  `http.response.start`, record status, and on completion (in `finally`) emit one access
  record on logger `backend.api.access` with `method`, `route` (matched template, else path),
  `status`, `latency_ms`, `user_id` — at `DEBUG` for `/health`, else `INFO`; register it in
  `create_app()`; verify `tests/test_api_request_id.py` shows the header on `/health`,
  `/api/foods`, a 401, and a streamed `/api/chat` (offline, seam overridden), echo of a valid
  incoming id, replacement of `not-a-uuid`, exactly one access record per request with the
  expected fields, and `/health` at `DEBUG`
- [x] 3.2 Set `user_id` in `get_current_user` once the user row is loaded, and
  `child_profile_id` in `owned_child` and in `resolve_chat_request` (both branches that yield
  a profile) in `backend/api/deps.py` and `backend/api/chat.py` — boundary: session and owned
  row only; verify a `db` test in `tests/test_api_request_id.py` shows the access record for
  `GET /api/children` carries the account id, and a chat through the seam yields
  `meal_plan_audit`/`nutrient_gaps_audit`/`rag`/`chat` records all carrying the same
  `request_id`, the account id, and the child profile id, with none of them changed in message
  text

## 4. Tool, retrieval, and error records

- [x] 4.1 In `backend/chat/service.py::_run_one`, time `tool.ainvoke` and emit one `INFO`
  record on logger `backend.chat.tools` with `extra` `tool`, `status`, `latency_ms`,
  `used_context`, and `error_kind` (validation / unknown_food / unsafe / failure) for errors;
  add `message_chars` to the routing summary; verify `tests/test_chat_service.py` gains a test
  asserting one tool record per invocation with those fields and that the message text is
  absent from every captured record, and `test_routing_log_line` still passes
- [x] 4.2 In `backend/rag/pipeline.py::retrieve`, time the retriever call and add
  `latency_ms` and `queries` as `extra` on the existing `rag` line (text unchanged); verify
  `tests/test_rag_pipeline.py` gains an assertion on the record's `latency_ms` and `queries`
  attributes and existing assertions hold
- [x] 4.3 Answer unhandled exceptions in `RequestContextMiddleware` (design Decision 6, revised
  at apply: Starlette's exception handlers run outside the request context): log one `ERROR`
  record with `exc_info` and return 500 `{"detail": <fixed copy in backend/chat/copy.py>,
  "request_id": ...}`; add `request_id` to the terminal SSE `error` event in
  `backend/api/chat.py` and `backend/api/ask.py`; verify `tests/test_api_request_id.py` shows
  a route that raises returns 500 with exactly those two keys and no traceback text, one error
  record with the request id is captured, and `tests/test_api_chat.py`'s mid-stream failure
  test asserts `request_id` on the error event

## 5. Never-logged guarantees and close-out

- [x] 5.1 Add to `tests/test_api_auth.py` (db) a test that registers and signs in with caplog
  at `DEBUG` on the root logger and asserts no captured record's message or attributes contain
  the password, its hash, the session cookie value, or the email; verify it passes. *Added at
  apply:* the live check found SQLAlchemy `echo` (dev only) printing bound parameters — email
  and hash — so `backend/db/session.py` now never echoes, pinned by
  `tests/test_logging.py::TestEngineNeverEchoes`
- [x] 5.2 Update `README.md` (Development: `LOG_FORMAT`, `LOG_LEVEL`, `AUDIT_LOG_PATH`,
  `--no-access-log`; Security: what is never logged; a "Logging and monitoring (Day 6)"
  section describing the record types and how to follow one request by `X-Request-ID`);
  verify `uv run ruff check . && uv run ruff format --check backend tests scripts alembic &&
  uv run pytest -q` are green and `openspec validate day-6-logging-and-monitoring --strict`
  passes
- [x] 5.3 Manual check with live services (`uv run uvicorn backend.main:app --port 8000
  --no-access-log`, `LOG_FORMAT=json`): sign in, ask "what's her BMI?", and confirm in the
  server output one access record, one routing record, one tool record, and that grepping the
  `X-Request-ID` from the response finds every record for that turn; then set
  `AUDIT_LOG_PATH` and confirm a meal-plan audit line lands in the file once
