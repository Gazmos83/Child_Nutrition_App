Groups 1–6 need no database and are verifiable on this machine today. Group 7 is the
database-dependent work, isolated deliberately (see design.md — Risks) so everything else
completes and verifies without a `DATABASE_URL`.

## 1. Toolchain and dependency baseline

- [x] 1.1 Add runtime deps with `uv add fastapi uvicorn[standard] sqlalchemy alembic asyncpg pydantic pydantic-settings` and verify `uv.lock` is updated and `uv sync` exits 0
- [x] 1.2 Add dev deps with `uv add --dev pytest pytest-asyncio ruff` and verify `uv run pytest --version` and `uv run ruff --version` both succeed
- [x] 1.3 Configure ruff and pytest (asyncio mode, testpaths) in `pyproject.toml`; verify `uv run ruff check .` exits 0 on the empty tree
- [x] 1.4 Extend `.gitignore` with `.env`, `.pytest_cache/`, `.ruff_cache/`; verify `git status --short` shows no ignored artifacts after a test run

## 2. Package structure

- [x] 2.1 Create the `backend/` package skeleton (`core/`, `db/`, `models/`, `schemas/`, `api/`) with `__init__.py` files; verify `uv run python -c "import backend"` succeeds
- [x] 2.2 Delete the placeholder `main.py` and verify no module still imports it (`grep -rn "from main\|import main" --include=*.py .` returns nothing)

## 3. Configuration

- [x] 3.1 Implement `backend/core/config.py` with a pydantic-settings `Settings` class reading `DATABASE_URL` and `APP_ENV`; verify a unit test asserts a `postgresql://` URL is normalized to `postgresql+asyncpg://` (design.md Risk 4)
- [x] 3.2 Verify `Settings` fails loudly with a readable message when `DATABASE_URL` is absent — unit test asserts the raised error names the missing field
- [x] 3.3 Write `.env.example` documenting `DATABASE_URL` (with the `+asyncpg` scheme) and `APP_ENV`; verify it is committed and `.env` is not

## 4. Controlled vocabularies

- [x] 4.1 Implement `backend/models/enums.py` with `Sex`, `DietPreference`, and `Allergen` as `enum.StrEnum`; `Allergen` covers the regulatory big nine (milk, egg, peanut, tree nut, soy, wheat, fish, shellfish, sesame)
- [x] 4.2 Verify `DietPreference` declares an explicit default member, satisfying the child-profile scenario *Unspecified preference has a defined default* — unit test asserts the default is a real member, not None
- [x] 4.3 Verify each enum's members are lowercase, underscore-free-text-free values via a unit test iterating members (keeps DB enum labels stable across migrations)

## 5. ORM models

- [x] 5.1 Implement `backend/db/base.py` with a SQLAlchemy 2.0 `DeclarativeBase` and a UUIDv7 primary-key mixin using `uuid.uuid7` (design.md Decision 3); verify a unit test asserts two generated ids are time-ordered and differ by more than 1
- [x] 5.2 Implement the `User` model — `id`, `email`, `hashed_password`, `is_active`, `created_at` — plus the `lower(email)` functional unique index (Decision 4); verify the index appears in `User.__table__.indexes`
- [x] 5.3 Implement the `ChildProfile` model with `age_in_months` (SmallInteger, CHECK 0–60), `weight_kg` (`Numeric(5,2)`, CHECK > 0), `sex`, `diet_preference`, `doctors_note`, `doctors_note_recorded_at`, and `user_id` FK with `ON DELETE CASCADE`; verify a unit test asserts no attribute or column named `age_years` exists anywhere on the model (hard rule 1)
- [x] 5.4 Add the paired doctor's-note CHECK (both null or both set, Decision 9); verify the constraint is present in `ChildProfile.__table__.constraints`
- [x] 5.5 Implement the `child_allergies` join table with composite PK `(child_profile_id, allergen)` and cascade delete (Decision 8); verify a unit test asserts the composite primary key has exactly two columns
- [x] 5.6 Wire the `ChildProfile.allergies` relationship and verify a unit test builds a profile with three allergens in memory and reads back three distinct values, not a joined string

## 6. Application entry point

- [x] 6.1 Implement `backend/db/session.py` with `create_async_engine`, `async_sessionmaker`, and a `get_db` dependency yielding `AsyncSession` (Decision 1)
- [x] 6.2 Implement `backend/main.py` as a FastAPI app factory mounting an `/api` router; verify `uv run python -c "from backend.main import app; print(len(app.routes))"` succeeds without a database connection
- [x] 6.3 Implement `GET /health` returning app status plus a database-reachability field that degrades gracefully (reports `"db": "unreachable"` rather than raising) when Postgres is absent; verify via FastAPI `TestClient` that it returns 200 with no `DATABASE_URL` set
- [x] 6.4 Confirm no user-scoped route is exposed (design.md Risk 6) — verify by asserting the app's route paths are exactly `/health` plus FastAPI's built-in docs routes

## 7. Database-dependent work — blocked until `DATABASE_URL` exists

- [ ] 7.1 Initialize Alembic and convert `alembic/env.py` to the async `run_async_migrations` pattern (Decision 1); verify `uv run alembic current` connects and prints an empty revision
- [ ] 7.2 Author the initial migration creating the three enum types, `users`, `child_profiles`, and `child_allergies`; verify `uv run alembic upgrade head` exits 0
- [ ] 7.3 Hand-write the migration's `downgrade()` to drop tables before enum types, with a comment on the `ALTER TYPE ... ADD VALUE` transaction restriction (design.md Risks); verify `alembic downgrade base` then `upgrade head` round-trips cleanly
- [ ] 7.4 Implement `tests/conftest.py` with an async engine fixture and per-test transaction rollback against the Postgres test database (Decision 12); verify `uv run pytest` collects and runs
- [ ] 7.5 Verify the age constraint against real Postgres — integration tests assert `-1`, `61`, and `8.5` are all rejected, and `0` and `8` accepted (child-profile spec, *Age is represented in months*)
- [ ] 7.6 Verify the allergen vocabulary against real Postgres — integration test asserts an off-vocabulary string raises a database error and that inserting the same allergen twice violates the composite PK
- [ ] 7.7 Verify email uniqueness is case-insensitive — integration test asserts `Parent@Example.com` then `parent@example.com` raises a uniqueness violation (user-account spec)
- [ ] 7.8 Verify cascade deletion — integration test asserts deleting a user removes its child profiles and their allergy rows, leaving no orphans (user-account spec, *Account deletion removes owned data*)
- [ ] 7.9 Verify weight precision — integration test asserts `8.4` and `8.45` round-trip exactly as `Decimal`, and that `0` is rejected
- [ ] 7.10 Add the `user-account` authorization scenarios as `xfail(reason="authz lands D6")` tests so D6 inherits a ready checklist (design.md Risk 6); verify the suite reports them as expected failures, not passes
- [ ] 7.11 Run `GET /health` against the live database and verify it reports the database as reachable
