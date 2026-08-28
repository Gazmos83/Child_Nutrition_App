## Context

The schema (`backend/models/`) exists but has never been migrated; `alembic/` did not
exist; `get_db` was dead code; no route took an identity; the child's details and the
feeding log lived in `localStorage` and travelled in every `POST /api/chat` body. The
frontend talks to one origin — `next.config.ts` proxies `/api/*` to FastAPI — and streams
with `fetch` + a hand-written SSE parser, not `EventSource`. Day 7 is deployment.

## Goals / Non-Goals

Goals: a real database with a round-tripping migration chain; accounts; every user-scoped
read and write bound to the authenticated account (hard rule 9) with tests as evidence;
the stored profile as the only authority for the numbers a plan is built from; `main`
still deployable at the end of the day.

Non-goals: see the proposal. In particular no conversation persistence and no multi-child
UI.

## Decisions

### 1. PostgreSQL in Docker, one service, loopback only

**Decision:** `docker-compose.yml` runs `postgres:17` bound to `127.0.0.1:5432` with a
named volume and an init script creating `nutrition_test`. Backend and frontend stay on
the host. Milvus Lite remains an embedded file.

**Why:** Day 1 Decision 11 made the database reachable through `DATABASE_URL` only, so the
host changes nothing in code. A disposable container makes the migration's
`downgrade()` cheap to iterate (`docker compose down -v`), pins the major version to what
deployment will run, and lets Day 7's image be rehearsed locally. Managed-only would have
meant developing against the deployment instance; a bare `apt` Postgres would have meant
`pg_hba.conf` work and a second provisioning on Day 7 anyway.

**Alternative considered:** compose the backend too. Rejected: it slows the reload loop and
turns Day 6 into Day 7.

### 2. `TEST_DATABASE_URL` is an explicit setting, not derived

**Decision:** `Settings.test_database_url: str | None`, validated like `database_url`;
`tests/conftest.py` reads only it. Absent → `db` tests skip with a reason; present but
unreachable → they fail.

**Why:** the fixtures run migrations and roll back transactions against it. A derived name
(`<db>_test`) would make a destructive default silent — on Day 7, with `DATABASE_URL` at
the deployed instance, a test run would connect to the production server. An explicit
variable means the suite physically cannot run unless a human named a test database.
Skipping when the variable is set but the server is down was rejected: silence would read
as success.

### 3. One hand-written migration; enum types created first, dropped last

**Decision:** `alembic/versions/…_initial_schema.py` declares the five enum types with
`create_type=False`, creates them explicitly before the tables, and drops them after the
tables in `downgrade()`. Values are literals, not imports from `backend.models.enums`.

**Why:** autogenerate creates types as a side effect of `create_table` but never drops them,
so `downgrade base` → `upgrade head` fails on the second `CREATE TYPE`. Literal values
keep the "initial" migration a snapshot — importing the live enum would silently change what
it creates when a member is added later. The `ALTER TYPE … ADD VALUE` transaction caveat is
written in the migration file itself. `tests/test_migrations.py` asserts the round-trip and
that the labels match the Python vocabularies, so the check does not rot.

### 4. `ActivityLevel` moves to `backend/models/enums.py`; the profile gains two columns

**Decision:** `ChildProfile.height_cm: Numeric(4,1) | None` and
`ChildProfile.activity_level` as a fifth PostgreSQL enum. `ActivityLevel` is defined with
the other vocabularies and re-imported by `backend/schemas/tools.py` under the same name.

**Why:** the stored profile must reproduce the whole `ChildContext` the chat and the tools
take, and both fields were already in the form. A controlled vocabulary belongs with the
others (hard rule 2). The move is a re-export, so no other import changes.

### 5. Session: signed JWT in an `HttpOnly`, `SameSite=Lax` cookie; argon2id passwords

**Decision:** `backend/auth/tokens.py` issues HS256 tokens (`sub`, `iat`, `exp`) with
`SESSION_SECRET`; `backend/api/auth.py` sets them as a cookie (`Secure` outside `dev`).
`backend/auth/passwords.py` wraps `argon2-cffi` with library defaults; login verifies against
a dummy hash when the email is unknown so timing is uniform. No session table, no refresh
token, no CSRF token.

**Why:** the app renders model-generated text into the DOM — an unusually live XSS surface —
so a token JavaScript can read is the wrong default; an `HttpOnly` cookie removes theft from
the threat model. Same-origin through the rewrite means the cookie rides along on every
existing `fetch` with no client plumbing, and the manual SSE parser means `EventSource`'s
header limitation never applies. Stateless tokens skip a third table; revocation-before-
expiry matters only for deactivated accounts, which `get_current_user` refuses anyway
because it re-reads the row. `SameSite=Lax` plus JSON-only bodies covers CSRF for an MVP
whose mutating routes are all non-navigational — which creates one standing rule: **no GET
may mutate**. `argon2-cffi` and `pyjwt` were verified to install on Python 3.14; `passlib`
(the tutorial default) does not import there, and `bcrypt` adds a 72-byte rule to police.

### 6. Two dependencies are the whole authorization surface

**Decision:** `backend/api/deps.py::get_current_user` (cookie → active `User` or 401 with
one fixed message) and `owned_child` (`child_id` AND `user_id == user.id` → profile or the
same 404 as a nonexistent id). No repository layer: routes query directly, and the list
route is the only query that filters by `user_id` itself.

**Why:** the ownership predicate written once cannot be forgotten by the next route.
Returning 404 rather than 403 satisfies the `user-account` scenario "does not reveal whether
that profile exists"; `tests/test_api_children.py` asserts the two responses are
byte-identical. A repository abstraction was deferred on Day 1 and never earned; with one
day left it would be the speculative layer the design warned about.

### 7. `POST /api/chat`: a wire body and a resolved request, seam in the API layer

**Decision:** `ChatRequestBody` (message, `child_id`, history, timezone, strategy, stream;
`extra="forbid"`) is the public contract. `ChatRequest` extends it with `child` and
`feeding_log` and is constructed only by `resolve_chat_request` in `backend/api/chat.py`,
which reads the account's rows. `backend/chat/` and its tests do not change. `child_id`
omitted means the account's only child; several children → 422 naming `child_id`; none →
no child context and the existing "details go in the side panel" path.

**Why:** hard rule 9 binds every user-scoped read to the account; if `child` stayed
client-supplied, the age, weight, and allergy set a meal plan is built from would remain
caller-controlled and the hard-rule-8 audit snapshot would record numbers nobody reviewed.
Placing the seam one layer above `resolve_context` keeps the routing package database-free
and leaves ~26k of router/service tests untouched; the offline chat-API tests override the
seam to accept a full `ChatRequest`, and the seam itself is tested against PostgreSQL.

### 8. The feeding log is stored as entries; nutrients are recomputed on every read

**Decision:** `feedings` stores what the parent reported (time, type, food id, quantity,
unit) and nothing derived. `GET /api/children/{id}/feedings` prices each row through the
unchanged `log_feeding`; a row whose food id the table no longer knows is logged and
skipped, not an error. `POST` is idempotent on the entry id, which is the UUID
`log_feeding` already assigns.

**Why:** the feeding-log spec requires every figure to come from the committed food table;
storing nutrients would be a second source of truth that goes stale when
`nutrition-data/foods.yaml` changes. Idempotency on the id lets the browser save a feed the
assistant logged mid-answer (the `tool` event carries it already identified) without a
second write path inside the chat service, which stays database-free.

### 9. `log_feeding` stays pure; the route writes the row

**Decision:** `backend/tools/feeding_log.py` is unchanged. The child-scoped route validates
and prices through it, then inserts. A model-invoked `log_feeding` mid-chat reaches the
database through the browser: `use-chat.ts` posts the tool event's entry to the child's
feedings route.

**Why:** the tool is also invoked by the model from inside `ChatService`, which is
deliberately database-free; giving it a row write would drag a session into the chat package
and its tests. The extra round-trip is accepted; a `feeding_writer` injected into the
service is the Day 7 cleanup if it matters.

### 10. Frontend: explicit Save, one child, one 401 handler

**Decision:** `use-child-context.ts` edits a local draft seeded from the account's first
profile and saves with an explicit button (POST when none, PUT when one). `use-feeding-log.ts`
is a query keyed by the child id with add/remove mutations. `lib/api.ts::fetchJson` is the
only place a 401 is noticed; `Providers` registers a handler that flips the session query to
signed-out. The stores keep their pure halves; the `localStorage` halves are deleted.

**Why:** saving to a server on every keystroke is wrong; the form already had a validated
"complete" state to save. One child per account in the UI is the cut that removes the
"which child?" question entirely while the API keeps supporting several. Because auth runs
in a FastAPI dependency before the `StreamingResponse` exists, a 401 can never arrive
mid-stream — the only case is a session expiring between load and send, handled once in
`use-chat.ts` with the conversation kept and retry available after sign-in.

### 11. `/api/ask` and `/api/foods` stay public

**Decision:** unchanged, no identity.

**Why:** neither reads user data (the `ask-api` spec says so), the food picker is used on
a screen that may precede sign-in, and the same-day RAGAs harness posts to `/api/ask`
without a session. Recorded so the two Day 6 workstreams cannot collide; unauthenticated
model spend on a deployed instance is a Day 7 decision.

### 12. `integration` tests are deselected by default; `db` is a separate marker

**Decision:** `addopts` gains `-m "not integration"`; a new `db` marker names the tests that
need the compose database and is included by default.

**Why:** a plain `uv run pytest` was making ~37 billable OpenRouter calls because the live
files self-skip only when the key or `milvus.db` is absent — both present on this machine —
while the README claimed the suite was offline. The database tests are cheap and local and
belong in the default run; the marker text says what each requires.

## Risks / Trade-offs

- **`TestClient` runs the app on its own event loop** → a session created in the test's loop
  cannot cross into it. `api_client` uses `httpx.AsyncClient(transport=ASGITransport(...))`;
  the non-DB API tests keep `TestClient`.
- **pytest-asyncio loop scoping** → a session-scoped async engine fails the same way.
  `db_engine` is function-scoped with `NullPool`; the schema fixture is a plain `def` running
  Alembic (which calls `asyncio.run()` itself), so nothing widens the loop scope for the ~640
  existing tests.
- **`alembic.ini` logging config would reconfigure the test process's root logger** →
  `env.py` skips `fileConfig` when `config.attributes["skip_logging_config"]` is set, which the
  conftest sets.
- **Stateless sessions cannot be revoked before expiry** → accepted; TTL is seven days, and
  deactivation is immediate because the user row is re-read per request.
- **`argon2` costs 64 MiB per hash** → fixture accounts share one precomputed hash; only the
  primitive tests hash for real. Password length is capped at 128 in the schema.
- **A stale tab 422s after the merge** → frontend and backend ship together; the validation
  message is surfaced verbatim in the chat.

## Migration Plan

1. `sudo apt install docker.io docker-compose-v2 && sudo usermod -aG docker $USER`; re-login.
2. `docker compose up -d`; `.env` gets `DATABASE_URL`, `TEST_DATABASE_URL`, `SESSION_SECRET`.
3. `uv run alembic upgrade head`; `uv run alembic downgrade base && uv run alembic upgrade head`.
4. `uv run pytest` (offline + `db`), `uv run ruff check .`, frontend lint/typecheck/test/build.
5. Manual E2E: register → save child → ask → log → reload → sign out → second account sees
   nothing of the first.
6. `/security-review`, `/code-review`; merge `--no-ff` into `main`; archive this change and
   `day-1-foundation-postgres`.

**Rollback:** `git switch main` — nothing on `main` depends on the branch; `docker compose
down -v` drops the local database.
