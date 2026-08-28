## Context

See `proposal.md` — Why. Constraints that actually shape the approach:

- **The repo is empty of code.** No prior patterns to match, so Day 1's choices become
  the project's conventions by default. They are worth deciding deliberately rather than
  drifting into.
- **No Postgres on this machine.** No server, no `psql`, no Docker, and no passwordless
  sudo. The schema can be authored and unit-tested, but a migration cannot be proven
  against real Postgres until a `DATABASE_URL` exists.
- **Six more days build on this.** D4 tools read child profiles; D5 streams responses over
  SSE; D6 attaches auth to `users`. Choices that are cheap now and expensive on D5 deserve
  the most scrutiny.
- **Two hard rules are safety rules, not style rules.** Age-in-months and no-free-text
  allergies exist because an infant meal plan built on a wrong age or a missed allergy is
  a real harm, not a bug report.

## Goals / Non-Goals

**Goals:**

- Make the three schema-level hard rules structurally impossible to violate — enforced by
  the database, not by convention or by trusting the LLM layer.
- Land a package layout that keeps HTTP, domain, and (later) AI concerns separable, so D3
  and D5 add modules instead of restructuring.
- Be verifiable the moment a `DATABASE_URL` exists, with no code changes required.

**Non-Goals (design-level, beyond the proposal's scope boundaries):**

- No repository/service abstraction layer yet — with one entity pair and no consumers, it
  would be speculative. D4 introduces it when tools need auth-scoped reads.
- No soft deletes or audit-history tables. Requirement *Profile inputs are recorded for
  auditability* is satisfied on D4 by snapshotting inputs into the recommendation log,
  not by versioning profile rows.
- No connection pooling tuning, read replicas, or query optimization.

## Decisions

### 1. Async SQLAlchemy 2.0 + asyncpg, not sync

**Decision:** `create_async_engine`, `AsyncSession`, `async_sessionmaker`, asyncpg driver,
and an async Alembic `env.py`.

**Why:** D5 requires SSE streaming of AI responses, and D3 puts LangChain calls in the
request path — both are I/O-bound and async-native. A sync stack works today and becomes
a rewrite of every route and session dependency on D5, precisely when the schedule is
tightest.

**Alternative considered:** sync SQLAlchemy + psycopg3. Genuinely simpler — plain Alembic,
plain pytest, no event-loop fixtures — and FastAPI runs sync endpoints in a threadpool.
Rejected because the conversion cost lands on the worst possible day. The async ceremony
is paid once, on Day 1, when there are two tables and no consumers.

**Cost accepted:** async test fixtures and an async Alembic env are more moving parts than
the sync equivalents.

### 2. Native PostgreSQL enum types for the controlled vocabularies

**Decision:** `Sex`, `DietPreference`, and `Allergen` become real PostgreSQL enum types,
mirrored by Python `enum.StrEnum` classes as the single source of truth.

**Why:** Hard rule 2 says allergies and diet preference are never free text. A native enum
makes that a database invariant — a bad value is rejected even if it arrives through a
migration, a manual `psql` session, or a future code path nobody reviewed. For a field
where a miss means feeding a child an allergen, the strongest available enforcement is the
right one.

**Alternatives considered:**

- *VARCHAR + CHECK constraint* — equally enforced, and easier to extend (no `ALTER TYPE`).
  Rejected as marginally weaker in intent: a `CHECK` is easy for a later migration to drop
  without anyone noticing, and the column type itself carries no meaning.
- *Lookup table + foreign key* — most flexible, and the natural home for per-allergen
  metadata later. Rejected for Day 1: it turns a closed vocabulary into runtime data,
  which means an allergen can be added by an `INSERT` rather than a reviewed migration.

**Cost accepted:** adding an allergen requires a migration, and `ALTER TYPE ... ADD VALUE`
has transactional restrictions — the new value cannot be used in the same transaction that
adds it. This is treated as a feature: for a safety-critical vocabulary, a new value
*should* be a deliberate, reviewed schema change. The allergen list is seeded from the
regulatory "big nine" (milk, egg, peanut, tree nut, soy, wheat, fish, shellfish, sesame),
which is stable, plus `none` handling via an empty association set rather than a sentinel.

### 3. UUIDv7 primary keys from the standard library

**Decision:** `uuid.uuid7()` (new in Python 3.14, already pinned) for all primary keys,
stored as native `UUID`.

**Why:** The `user-account` spec requires identifiers that cannot be derived by
incrementing — a sequential integer PK in a URL is an enumeration vector against a
children's health record. UUIDv7 is time-ordered in its high bits, so it keeps the index
locality that made bigserial attractive, while the random tail defeats guessing. No
dependency needed.

**Alternatives considered:** `bigserial` (rejected — enumerable); UUIDv4 (rejected — random
across the whole value, causing B-tree page splits and index bloat as tables grow).

### 4. Case-insensitive email via a functional unique index

**Decision:** store email as written, enforce uniqueness with a unique index on
`lower(email)`.

**Why:** satisfies the *Email comparison ignores case* scenario without requiring the
`citext` extension, which some managed Postgres providers restrict. Preserving the
user's original casing is also friendlier for display and for mail delivery.

**Alternative considered:** `citext` column (rejected — an availability assumption about
the host); lower-casing on write (rejected — destroys user input irreversibly).

### 5. Email + password hash on the `users` table

**Decision:** `users(id, email, hashed_password, is_active, created_at)`, with
`hashed_password` NOT NULL.

**Why:** self-contained, no vendor in the critical path, and D6 adds only JWT issuance and
verification on top. NOT NULL rather than nullable because a nullable password column
encodes an invariant the database cannot enforce ("either a password or an external
subject, never neither").

**Alternative considered:** an external IdP subject (Clerk/Auth0/Supabase). Rejected for
MVP — it adds a vendor and a frontend SDK to a 7-day build, and the course requirement is
to demonstrate auth, not to outsource it. Migrating later is an additive column plus a
backfill, not a redesign.

**Note:** no hashing library is added on Day 1 — the column exists, but nothing writes to
it until D6, so the algorithm choice (argon2 vs bcrypt) stays a D6 decision.

### 6. Weight as `Numeric(5,2)` kilograms

**Decision:** fixed-point `Numeric(5,2)`, unit documented as kilograms in the column
comment and the Pydantic schema.

**Why:** nutrient targets are computed per kilogram, so weight feeds arithmetic whose
result is a feeding instruction. Binary floating point introduces representation error
into that chain for no benefit. `Numeric(5,2)` covers 0.01–999.99 kg — far beyond a
4-year-old — and preserves the recorded precision the spec asks for.

**Alternative considered:** `double precision` (rejected — float error in a safety
calculation); integer grams (rejected — correct, but every read and write needs a
conversion, inviting unit-confusion bugs of exactly the kind this project must avoid).

### 7. Age as `SmallInteger` with a database CHECK constraint

**Decision:** `age_in_months SMALLINT NOT NULL CHECK (age_in_months BETWEEN 0 AND 60)`,
and deliberately **no** `age_years` column anywhere in the schema.

**Why:** hard rule 1 is enforced by the absence of an alternative. There is no years column
to accidentally read, so the failure mode ("someone used age in years") cannot be
expressed. The CHECK covers the spec's negative-age and out-of-range scenarios at the
database level; the integer type covers the fractional-age scenario by rejecting `8.5`
rather than silently truncating it.

### 8. Allergies as a join table with a composite primary key

**Decision:** `child_allergies(child_profile_id, allergen)` with `PRIMARY KEY
(child_profile_id, allergen)` and `ON DELETE CASCADE`.

**Why:** the composite PK *is* the deduplication guarantee — the *Duplicate allergen not
double-recorded* scenario becomes a database invariant rather than application logic that
could be bypassed. "No allergies" is the natural empty set, needing no sentinel row.

**Alternative considered:** a Postgres array column `allergens Allergen[]` (rejected —
arrays cannot express uniqueness declaratively and are clumsier to query and join).

### 9. Doctor's note as two columns, not a history table

**Decision:** `doctors_note TEXT NULL` and `doctors_note_recorded_at TIMESTAMPTZ NULL` on
`child_profiles`, with a CHECK that both are null or both are set.

**Why:** the spec requires the note text and its recording time to be retrievable — two
columns satisfy that. The day plan calls for a "doctor's note field", and a note-history
table would be speculative before D4 shows how the override logic reads it. The paired
CHECK keeps "a note with no timestamp" out of the database.

**Deferred:** the note is stored as free text on purpose — it is clinician input, not a
system vocabulary. D4 owns parsing it into structured overrides; Day 1 only guarantees it
is captured with provenance. Note that hard rule 2's no-free-text constraint applies to
allergies and diet preference, not to this field.

### 10. All timestamps are `TIMESTAMPTZ`, defaulted server-side

**Decision:** `TIMESTAMPTZ` with `server_default=func.now()`.

**Why:** naive timestamps in a health record are ambiguous, and server-side defaults mean
the database, not the application clock, is the authority — consistent across the app,
migrations, and manual fixes.

### 11. Managed PostgreSQL, reached only through `DATABASE_URL`

**Decision:** the application knows nothing about how Postgres is hosted; a single
`DATABASE_URL` in `.env` (gitignored, with a committed `.env.example`) is the entire
contract. No Docker Compose file on Day 1.

**Why:** Docker is not installed and installing it needs sudo I should not assume. Section
15 targets managed Postgres for deployment anyway, so developing against a free managed
instance (Neon/Supabase) removes an environment difference rather than adding one. If a
local Postgres is preferred later, it is a one-line `.env` change and no code change.

> **Superseded 2026-08-28** by `day-6-auth-and-persistence` Decision 1: Docker was installed
> and a pinned `postgres:17` service in `docker-compose.yml` backs both the development and
> the test database. The reasoning above held and its prediction was borne out — switching
> was a one-line `.env` change and no code change. Deployment still targets a managed
> instance, reached through the same `DATABASE_URL`.

### 12. Tests run against real PostgreSQL, not SQLite

**Decision:** pytest fixtures point at a Postgres test database; there is no SQLite
fallback.

**Why:** every enforcement decision above — native enums, `TIMESTAMPTZ`, `Numeric`,
functional unique indexes, composite-PK cascades — behaves differently or not at all on
SQLite. A green SQLite suite would prove nothing about the invariants that make the schema
safe, which is worse than no suite: it would be actively misleading.

**Consequence, stated plainly:** the tests are written on Day 1 but **cannot be run until a
`DATABASE_URL` exists**. This is the one part of Day 1 that ends unverified, and it is a
deliberate trade rather than an oversight. See Risks.

## Risks / Trade-offs

- **Migration and tests unverified until a database exists** → Every task that needs a live
  database is grouped into one clearly-marked section of `tasks.md`. Nothing else depends
  on it, so the rest of Day 1 completes and verifies independently. The first command run
  against a real `DATABASE_URL` will be `alembic upgrade head` followed by the suite, and
  schema-level mistakes will surface there in minutes.
- **Async adds ceremony to a 7-day build** → Confined to three files (`db/session.py`,
  `alembic/env.py`, `tests/conftest.py`). Route and model code reads almost identically to
  the sync version.
- **Native enums make vocabulary changes a migration** → Accepted deliberately (Decision 2).
  The one real trap is `ALTER TYPE ... ADD VALUE` inside Alembic's transaction; documented
  in the migration file itself so the next person hits the note before the error.
- **`asyncpg` requires the `postgresql+asyncpg://` URL scheme** → A plain `postgresql://`
  URL copied from a provider dashboard fails at startup with an unhelpful driver error.
  Settings validation normalizes the scheme and fails loudly with a clear message instead.
- **UUID PKs are wider than integers** → Irrelevant at this scale, and UUIDv7's time
  ordering avoids the index fragmentation that would have been the real cost.
- **Day 1 lands `user_id` foreign keys but no enforcement** → The `user-account` spec's
  authorization scenarios are written now and cannot pass until D6. To avoid shipping an
  unprotected read path in the meantime, Day 1 exposes **no** user-scoped endpoints at all
  — only `/health`. The authorization tests are marked `xfail` with an explicit reason
  rather than omitted, so D6 has a checklist that already exists and turns green.

## Migration Plan

1. `uv sync` to install the new dependency set.
2. Create a managed Postgres instance; put its URL in `.env` as `DATABASE_URL` using the
   `postgresql+asyncpg://` scheme.
3. `uv run alembic upgrade head` — creates three enum types, `users`, `child_profiles`,
   `child_allergies`.
4. `uv run pytest` — model and constraint tests; authorization tests report `xfail`.
5. `uv run uvicorn backend.main:app --reload`, then `GET /health` to confirm the app boots
   and reaches the database.

**Rollback:** `uv run alembic downgrade base`. The initial migration's `downgrade()` drops
the tables and then the enum types, in that order — enum types must be dropped after the
columns that reference them, which Alembic does not generate automatically and is written
by hand here.

## Open Questions

None that block implementation. Three decisions above (1, 5, and 11 — async, password-based
auth, and managed Postgres) were made without confirmation and are the ones most worth a
second opinion before the code lands; each records its alternative and the cost of
switching, and none of the three would change the specs or the task breakdown if reversed.
