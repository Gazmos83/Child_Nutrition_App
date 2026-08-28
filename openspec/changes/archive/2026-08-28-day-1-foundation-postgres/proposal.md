## Why

The repo currently holds documentation and an empty `main.py` — there is no application
code, no database, and no backend package structure. Day 1 of the 7-day plan exists to
lay a foundation that the remaining six days bolt onto without rework: the domain model
for users and child profiles, and the PostgreSQL schema that is the authoritative store
for them.

This has to come first because three of the project's hard rules are *schema* rules —
age in months, allergies and diet preference as controlled vocabularies, and per-user
data isolation. Encoding them in the database on Day 1 makes them structurally
impossible to violate later, rather than conventions the LLM pipeline is trusted to
respect.

**Scope: [MVP]. Day 1 of 7.**

## What Changes

- **Backend package structure** — a `backend/` FastAPI application laid out so HTTP
  concerns, domain models, and (later) AI logic stay separate: `api/`, `models/`,
  `schemas/`, `db/`, `core/`.
- **Dependency baseline** — FastAPI, SQLAlchemy 2.x, Alembic, Pydantic, pydantic-settings,
  asyncpg added via `uv add`; pytest, pytest-asyncio, ruff via `uv add --dev`. `uv.lock`
  stays authoritative.
- **Typed settings** — environment-driven configuration (`DATABASE_URL`, app env) via
  pydantic-settings, with a committed `.env.example` and `.env` gitignored.
- **Controlled vocabularies as database enums** — `Allergen`, `DietPreference`, and `Sex`
  become PostgreSQL enum types. Free-text allergy entry becomes representationally
  impossible.
- **`users` table** — the identity anchor every user-scoped row hangs off.
- **`child_profiles` table** — `age_in_months` as an integer (there is no `age_years`
  column to misuse), weight, sex, diet preference, a doctor's-note field, and a
  `user_id` foreign key that is the authorization boundary.
- **`child_allergies` join table** — many-to-many against the `Allergen` enum, so a
  child can carry multiple allergies without a delimited string.
- **Alembic migration chain** — configured for async SQLAlchemy, with the initial
  migration creating the enums and both tables.
- **Health endpoint + DB connectivity check** — `GET /health` proving the app boots and
  can reach Postgres.
- **Test baseline** — pytest configured, with tests covering the model constraints that
  matter (age-in-months validity, enum rejection of free text, cascade behavior).

## Capabilities

### New Capabilities

- `user-account`: A registered user identity — the anchor for authorization. Establishes
  that every user-scoped record is owned by exactly one user, and that ownership is the
  boundary enforced on all later reads and writes.
- `child-profile`: A child's nutrition profile owned by a user — age in months, weight,
  sex, diet preference, allergies, and an optional doctor's note. Establishes the
  controlled vocabularies, the months-only age representation, and the precedence of a
  doctor's note over general nutrient targets.

### Modified Capabilities

None — this is the first change in the project; `openspec/specs/` is empty.

## Impact

- **New code**: `backend/` package (app factory, settings, DB session, models, initial
  API router), `alembic/` migration environment, `tests/`.
- **Dependencies**: adds the FastAPI/SQLAlchemy/Alembic/asyncpg stack to `pyproject.toml`
  and `uv.lock`.
- **Infrastructure**: requires a reachable PostgreSQL instance, configured by `DATABASE_URL`
  only. *Written on Day 1:* no Postgres server, Docker, or client was installed on the
  machine and a managed instance was expected, so this change was written to be verifiable
  the moment that URL existed. *Amended 2026-08-28:* Docker was installed and a pinned
  `postgres:17` service in `docker-compose.yml` now backs both the development and the test
  database (`day-6-auth-and-persistence`, Decision 1); group 7 was verified against it. The
  `DATABASE_URL`-only contract held, as Decision 11 predicted — no code changed.
- **Downstream days**: D2 ingestion writes to Milvus only and does not touch this schema.
  D4 tools read `child_profiles` through auth-scoped repository code. D6 auth attaches
  credential verification to the `users` table already in place.
- **No breaking changes** — nothing exists to break.

## Non-goals

Deliberately deferred, to protect Day 1 from turning into Day 4:

- **Meals, meal items, daily nutrition, conversations, messages tables** — these belong
  with the features that use them (D4 tools, D5 chat UI). Adding them now would mean
  guessing at columns before the consuming code exists.
- **Authentication and authorization enforcement** — Day 6. Day 1 lands the `users` table
  and the `user_id` foreign keys that authorization will *use*, but no login, password
  verification, session handling, or dependency-injected current-user. Until D6, routes
  must not expose user-scoped data.
- **Milvus, LangChain, OpenRouter, embeddings** — D2 and D3. No AI dependencies are added.
- **Next.js frontend** — D5. Node 24 and pnpm are now installed, but no frontend project
  is scaffolded.
- **Nutrient lookup tables and the infant-safety filter** — D4.
- **Docker packaging and CI** — D7.
