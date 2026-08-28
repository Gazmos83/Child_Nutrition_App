## Why

Five days in, the app has a PostgreSQL schema that has never been migrated, a `users` table
nothing writes to, and a `get_db` dependency nothing imports. The child's details and the
feeding log live in the browser's `localStorage` and travel with every request, which the
Day 5 specs state plainly as a temporary arrangement ("client-held today", "until
authentication and the feeding-log table ship"). Hard rule 9 — every user-scoped read and
write bound to the authenticated identity, auth before deployment — is therefore unmet the
day before deployment, and the `user-account` spec's three authorization scenarios, written
on Day 1 to be satisfied on Day 6, have no code behind them.

This change makes the database real, adds accounts, moves the child profile and the
feeding log onto them, and closes `day-1-foundation-postgres` group 7 in passing. It is the
one Day 6 workstream that is not additive — every route gains an identity and the frontend
grows a sign-in — so it is developed on a branch and merged whole.

**Scope: [MVP]. Day 6 of 7, first workstream, before logging and the RAGAs evaluation.**

## What Changes

- **A local PostgreSQL** — Docker installed; a single pinned `postgres:17` service in
  `docker-compose.yml`, bound to loopback, creating a development and a separate test
  database. The backend and frontend are not containerized (Day 7 scope). Milvus Lite stays
  an embedded file.
- **Alembic initialized, one hand-written migration** — five enum types (`sex`,
  `diet_preference`, `allergen`, `feeding_type`, `activity_level`) created before the tables
  and dropped after them in `downgrade()`, so `downgrade base` → `upgrade head` round-trips.
  Tables: `users`, `child_profiles` (now also `height_cm`, `activity_level`),
  `child_allergies`, and the new `feedings`.
- **Authentication** — `POST /api/auth/register|login|logout`, `GET /api/auth/me`. Passwords
  hashed with argon2id; the session is a signed token in an `HttpOnly`, `SameSite=Lax`
  cookie. `get_current_user` and `owned_child` in `backend/api/deps.py` are the dependencies
  every user-scoped route runs behind.
- **Persisted child profiles and feeding log** — `GET/POST /api/children`,
  `GET/PUT/DELETE /api/children/{id}`, `GET/POST /api/children/{id}/feedings`,
  `DELETE /api/children/{id}/feedings/{feeding_id}`. A non-owner receives exactly the response
  a nonexistent id would.
- **`POST /api/chat` reads the child and the log from the account** — the body carries
  `child_id` (optional when the account has one child) instead of `child` and `feeding_log`;
  the seam that fills them from the account's rows lives in `backend/api/chat.py`, and
  `backend/chat/` is untouched. `POST /api/feedings` is removed; `GET /api/foods` and
  `POST /api/ask` stay public.
- **Frontend** — sign-in / create-account screen gating the chat; the child form saves to
  the account with an explicit Save; the feeding log is read from and written to the
  account; a 401 mid-session returns the parent to sign-in with the conversation kept.
- **Test infrastructure** — `tests/conftest.py` (did not exist): the real migration chain run
  once per session against `TEST_DATABASE_URL`, per-test transaction rollback, an ASGI client
  with `get_db` bound to the test session, fixture accounts. `pytest` now deselects
  `integration` tests by default — previously a plain `uv run pytest` made ~37 live
  OpenRouter calls while the README said it was offline.

## Capabilities

### New Capabilities

- `authentication`: an account is an email and a password kept only as a slow one-way hash;
  a session is a signed, expiring token in a cookie script cannot read and a cross-site
  request cannot send; sign-in failure does not reveal which credential was wrong; a
  deactivated account is refused on its next request.

### Modified Capabilities

- `user-account`: the ownership scenarios written on Day 1 are now satisfied, and the
  refusal is specified as indistinguishable from absence at the HTTP level.
- `child-profile`: profiles are reachable only through the owning account; a profile
  carries height and activity level so it can reproduce the full chat context.
- `chat-api`: reverses "reads and writes no user data" — the endpoint is authenticated and
  answers for the account's child; `child` and `feeding_log` leave the body; `child_id`
  joins it; `/api/feedings` is removed.
- `feeding-log`: replaces "client-held today" with per-child storage read only by the
  owning account, priced from the food table on every read.
- `chat-ui`: the parent signs in before using the assistant; the child form saves to the
  account rather than the browser; the log is the account's.

## Impact

- **New code**: `docker-compose.yml`, `scripts/db-init/01-test-db.sql`, `alembic/`,
  `backend/auth/{passwords,tokens}.py`, `backend/api/{deps,auth,children}.py`,
  `backend/schemas/{auth,child}.py`, `backend/models/feeding.py`, `tests/conftest.py`,
  `tests/test_{auth_primitives,api_auth,api_children,db_constraints,migrations}.py`,
  `frontend/src/lib/api.ts`, `frontend/src/hooks/use-session.ts`,
  `frontend/src/components/auth/auth-form.tsx`, `frontend/src/app/app-gate.tsx`.
- **Touched code**: `backend/core/config.py` (`TEST_DATABASE_URL`, `SESSION_SECRET`,
  `SESSION_TTL_HOURS`), `backend/models/{enums,child_profile,__init__}.py` (`ActivityLevel`
  moves to the vocabularies module; height and activity columns), `backend/schemas/chat.py`
  (`ChatRequestBody`), `backend/api/{chat,router}.py`, `pyproject.toml` (argon2-cffi, pyjwt,
  pydantic[email]; `-m "not integration"`; `db` marker), `tests/test_{app,api_chat,
  schemas_chat,config}.py`, the frontend hooks, stores, side panel, chat page, and copy.
- **Removed**: `backend/api/feedings.py`; the `localStorage` halves of
  `child-context-store.ts` and `feeding-log-store.ts`.
- **Dependencies**: `argon2-cffi`, `pyjwt`, `pydantic[email]` (all verified on Python 3.14;
  `passlib` does not import there).
- **Behaviour**: a stale browser tab sends `child` and receives 422 — frontend and backend
  ship in one merge. Sessions are stateless: logout clears the cookie and the token stays
  valid until expiry; a deactivated or deleted account is refused immediately because every
  request re-reads the user row.
- **Data / security**: hard rule 9 is enforced in two functions and evidenced by
  `tests/test_api_children.py`. The meal-plan audit snapshot (hard rule 8) is unchanged in
  content; its values now originate from the stored profile.

## Non-goals

- **Conversation persistence** — history stays client-supplied; it is text the same user
  typed a minute ago and buys nothing for hard rule 9.
- **Refresh tokens, server-side sessions, CSRF tokens, an Origin allowlist, rate limiting,
  email verification, password reset** — `SameSite=Lax` plus JSON-only bodies is the MVP
  CSRF posture; the rest is Day 7 hardening if time allows.
- **Migrating existing `localStorage` data** into the account — there are no users yet.
- **Multi-child UI** — the API supports several children per account and requires
  `child_id` when there are several; the UI edits one.
- **Authenticating `/api/ask`** — it reads no user data and the evaluation harness posts to
  it without a session. Revisit for deployment.
- **A spec for `docker-compose.yml`** — development infrastructure is not a product
  capability; it is documented in the README.
- **Application Dockerfile and CI** — Day 7.
