Developed on branch `day-6-auth-and-persistence`, merged `--no-ff` after review. Every task
touching user-scoped data states its authorization boundary. Groups 1–5 were written before
the database existed and verified against it once Docker was installed.

## 1. Database

- [x] 1.1 Create `docker-compose.yml` (`postgres:17`, loopback-only port, named volume,
  healthcheck) and `scripts/db-init/01-test-db.sql` (creates `nutrition_test`); point `.env`
  and `.env.example` at it; add `TEST_DATABASE_URL` to `Settings` with the same scheme
  validation; verify `tests/test_config.py` covers absent, normalized, and rejected test URLs
- [x] 1.2 `alembic init -t async alembic`; `env.py` takes the URL from `Settings` unless preset,
  imports `backend.models` for `Base.metadata`, and skips logging config when asked;
  `alembic.ini` leaves `sqlalchemy.url` empty and names files by date
- [x] 1.3 Add `Feeding` (`backend/models/feeding.py`), move `ActivityLevel` to
  `backend/models/enums.py` (re-exported by `schemas/tools.py`), add `height_cm` and
  `activity_level` to `ChildProfile`; verify the offline model/enum/schema tests pass
- [x] 1.4 Hand-write the initial migration: five enum types created before the tables and
  dropped after them, `uq_users_email_lower` as an expression index, all constraints named by
  the naming convention, the `ALTER TYPE … ADD VALUE` note in the file
- [x] 1.5 Verify against the container: `uv run alembic upgrade head`, then
  `uv run alembic downgrade base && uv run alembic upgrade head` exit 0; `GET /health` reports
  `reachable` (closes Day 1 tasks 7.1–7.3, 7.11)

## 2. Test infrastructure

- [x] 2.1 Create `tests/conftest.py`: `db` marker skip when `TEST_DATABASE_URL` is unset; a
  sync session fixture running Alembic to `head`; function-scoped `NullPool` engine; a session
  in a rolled-back outer transaction with savepoint commits; `api_client` over
  `ASGITransport` with `get_db` and `get_auth_settings` overridden; `user`, `other_user`,
  `auth_client` fixtures sharing one precomputed argon2 hash
- [x] 2.2 `pyproject.toml`: `addopts` deselects `integration`; register the `db` marker
- [x] 2.3 Write `tests/test_db_constraints.py` (Day 1 tasks 7.5–7.9: age range and integer,
  allergen vocabulary and composite PK, case-insensitive email, cascade to allergies and
  feedings, weight precision, note pairing, feeding quantity/unit rules) and
  `tests/test_migrations.py` (round-trip; labels match the Python enums)
- [x] 2.4 Verify `uv run pytest` is green with the container up, including every `db` test
  (closes Day 1 tasks 7.4–7.9)

## 3. Authentication

- [x] 3.1 `uv add argon2-cffi pyjwt "pydantic[email]"`; `backend/auth/passwords.py`
  (argon2id; dummy-hash verify for unknown emails; 8–128 chars) and
  `backend/auth/tokens.py` (HS256; `exp` required; non-UUID subject rejected); verify
  `tests/test_auth_primitives.py`
- [x] 3.2 `Settings.session_secret` (≥32 chars, optional) and `session_ttl_hours`;
  `.env.example` documents generation; `backend/api/deps.py::get_auth_settings` returns 503
  naming `SESSION_SECRET` when absent
- [x] 3.3 `backend/api/deps.py::get_current_user` — cookie → active user or 401 with one fixed
  message; `owned_child` — `child_id AND user_id` or the fixed 404 (authorization boundary
  for every child-scoped route)
- [x] 3.4 `backend/api/auth.py`: register (201, 409 on duplicate via the DB index), login
  (uniform 401, inactive refused), logout (clears cookie), me; cookie `HttpOnly`,
  `SameSite=Lax`, `Secure` outside dev; `backend/schemas/auth.py`
- [x] 3.5 Invert `tests/test_app.py`'s route-surface class: public set, user-scoped set, a loop
  over the OpenAPI schema asserting 401 on every user-scoped operation, 503 without a secret
- [x] 3.6 Verify `tests/test_api_auth.py` against the container: cookie attributes, duplicate
  409, wrong password ≡ unknown email, tampered/expired/deleted/deactivated → 401, logout

## 4. Persistence and the chat seam

- [x] 4.1 `backend/schemas/child.py` (`ChildProfileWrite` mirrors `ChildContext`;
  `ChildProfileResponse`) and `backend/api/children.py`: list (filters by `user_id`), create,
  get/put/delete through `owned_child`; a changed note is re-dated, a cleared one nulls both
  columns
- [x] 4.2 Feeding routes under `/api/children/{child_id}/feedings` (`owned_child`): list the
  last N days priced through `log_feeding`; create idempotent on the entry's UUID; delete
  checks the row belongs to the child. Remove `backend/api/feedings.py`; `tests/test_api_feedings.py`
  becomes `tests/test_api_foods.py`
- [x] 4.3 `ChatRequestBody` / `ChatRequest` split in `backend/schemas/chat.py`;
  `resolve_chat_request` in `backend/api/chat.py` (owned child by id, sole child when omitted,
  422 when several, none → no context); `backend/chat/` untouched; offline
  `tests/test_api_chat.py` overrides the seam; `tests/test_schemas_chat.py` covers the body
- [x] 4.4 `backend/api/router.py` includes auth and children; docstring states the public /
  authenticated split and why `/api/ask` stays public
- [x] 4.5 Verify `tests/test_api_children.py` against the container: owner-only listing;
  byte-identical 404 for non-owner and nonexistent across all six child-scoped operations;
  401 with no record data; feeding log read back priced, idempotent re-post, delete; the chat
  seam reads child and log from rows, rejects `child` in the body, requires `child_id` with
  two children, refuses an unowned id like a nonexistent one (closes Day 1 task 7.10 — written
  as passing tests, since authorization lands the same day)

## 5. Frontend

- [x] 5.1 `src/lib/api.ts` (`fetchJson`, `ApiError`, `readDetail`, unauthorized handler);
  `src/hooks/use-session.ts`; `src/components/auth/auth-form.tsx`; `src/app/app-gate.tsx`
  gating `ChatPage`; `Providers` registers the 401 handler; verify `api.test.ts`
- [x] 5.2 `child-context-store.ts` keeps validation, gains `fromProfile`, loses `localStorage`;
  `use-child-context.ts` is query + draft + save/clear mutations; `ChildContextForm` gains
  Save with saved/unsaved state and a failure line
- [x] 5.3 `feeding-log-store.ts` keeps the pure helpers; `use-feeding-log.ts` is a query keyed
  by child id with add/remove mutations; `LogFeedForm` takes a `submit` function;
  `FeedingLogTab` explains when no child is saved yet
- [x] 5.4 `use-chat.ts` sends `child_id` and `timezone`, handles 401 with `SESSION_EXPIRED`
  and the unauthorized handler, and hands a model-logged feed to the account's log;
  `chat-page.tsx` shows the account email and Sign out; `api-types.ts` and `copy.ts` updated
- [x] 5.5 Verify `pnpm -C frontend lint && typecheck && test && build` exit 0 (copy snapshot
  updated; store tests trimmed to the pure halves)

## 6. Close-out

- [x] 6.1 README: status, Security (mechanism, the two dependencies, evidence), Development
  (compose, Alembic, markers), Configuration; amend `day-1-foundation-postgres` proposal and
  design for Docker
- [x] 6.2 Manual E2E with live services: register → save child → "what's her BMI?" → log a
  feed → reload (both persisted) → sign out → second account sees nothing of the first
- [ ] 6.3 `/security-review` and `/code-review` on `git diff main...day-6-auth-and-persistence`;
  merge `--no-ff`; check off Day 1 group 7; archive both changes;
  `openspec validate day-6-auth-and-persistence --strict` passes
