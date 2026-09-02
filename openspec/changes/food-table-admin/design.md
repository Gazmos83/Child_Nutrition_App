## Context

See proposal.md — Why. Relevant current state:

- `backend/nutrition/foods.py`: `FoodItem` (frozen, `extra="forbid"`; the three safety
  booleans are required, `min_age_months` 0–60), `FoodTable {version, source, foods}`,
  `load_food_table(path)` with `_describe` (errors named `foods[i] (id).field`) and a
  duplicate-id check, `get_food_table()` as an `lru_cache`, `LoadedFoodTable` (id map,
  resolution index, `foods`, `get`, `resolve`, `matches`, `version`). Consumers: the nutrient
  tools, the planner (`table.foods`, `table.version` in the audit), the feeding log
  (`normalise_entry` → `get`), the API (`/api/foods` picker; feeding lists; growth curves
  unaffected). Every `tests/test_tools_*.py` and `create_app()` without a database call
  `get_food_table()` with no database; `tests/test_app.py::TestCors` asserts `/api/foods`
  answers with an unreachable `DATABASE_URL`.
- `backend/models/feeding.py` keeps `food_id` a string, not a foreign key ("the table is a
  versioned YAML file, not a database relation"). `MILK_FEED_DEFAULTS` (feeding) and
  `MILK_FEED_PRIORITY` (planner) hard-wire `breast_milk` and `infant_formula_iron_fortified`.
- Auth: `backend/api/deps.py` (`get_current_user`, `CurrentUser`, `owned_child`),
  `backend/core/config.py` (`allowed_origins` parsed with `NoDecode` + a `mode="before"`
  splitter), `backend/api/rate_limit.py` (`Bucket = Literal["model", "auth"]`),
  `backend/schemas/auth.py:CurrentUserResponse {id, email}`, `backend/api/auth.py` documents
  the CSRF posture as `SameSite=Lax` plus JSON-only bodies. `python-multipart` is not a
  dependency. `tests/test_app.py` pins `PUBLIC_PATHS | USER_SCOPED_PATHS` and loops every
  user-scoped operation asserting 401 without a session.
- `render.yaml` runs one instance; `scripts/start.sh` runs `alembic upgrade head` before
  uvicorn. Migrations are hand-written; head is `c3f8a2e2d003`.
- Frontend: `useSession` (`CurrentUser {id, email}`), `fetchJson`/`ApiError`, `useFoods`
  reads `/api/foods` for the picker, shadcn primitives (no Table), `copy.ts` snapshot test
  forbids prose literals in components, radio-group buttons in `log-feed-form.tsx`.

## Goals / Non-Goals

**Goals:**
- One write path that validates the whole table with the existing model, so the admin can
  never produce a table the loader would reject.
- Exact reproducibility of any plan's table (`db-<n>` names a stored snapshot).
- No change to how tools read the table (`LoadedFoodTable` stays the in-memory shape); no
  change to unit tests that read the committed file.
- The safety flags and the source are unavoidable in every form and every import.

**Non-Goals:**
- Anything under proposal.md — Non-goals.

## Decisions

### 1. Whole-table JSONB snapshots, one row per write

**Decision:** `food_table_revisions(revision INTEGER PK not autoincrement, table JSONB
{source, foods[]}, actor_user_id UUID FK users SET NULL, summary TEXT, created_at)`, CHECK
`revision >= 1`. A write loads the latest snapshot, applies the change in memory, validates
`FoodTable.model_validate(...)` (+ duplicate ids), and inserts `latest + 1`; a primary-key
collision (two admins at once) is a 409 "the table changed; reload".

**Why:** Every write is validated exactly as the file is, in one place; a plan's
`food_table_version` names a row that reproduces byte-for-byte what the planner saw (hard rule
8); nothing in the app queries foods relationally, and the feeding log deliberately does not
reference foods by foreign key. ~25 KB per snapshot; hundreds of writes are a few MB.

**Alternatives:** a relational `foods` table plus allergen join plus a version counter plus
an audit log — more code and two truths for "what was version N"; YAML base plus database
overrides — merge semantics nobody can reason about.

### 2. The loader keeps one in-memory shape; the cache becomes settable

**Decision:** `foods.py` replaces the `lru_cache` with a module-level `_TABLE`:
`get_food_table()` returns it or lazily loads the committed file (logging a warning that the
file is being served); `set_food_table(table)` swaps it atomically; `reset_food_table_cache()`
clears it (name kept for tests); `table_from_revision(revision, payload)` validates a snapshot
and sets `version = f"db-{revision}"`. `backend/main.py` gains a lifespan step that loads the
latest revision when the database is configured: `prod` raises on failure, other environments
warn and keep the file. Invalidation after a write is `set_food_table(...)` in-process — exact
because the service runs as one instance (documented the way `rate_limit.py` documents the
same fact).

**Why:** Every tool keeps calling `get_food_table()`; unit tests and a dev boot without a
database behave as today. `httpx.ASGITransport` in tests does not run the lifespan, so
database tests start from the file and admin writes set the cache directly; an autouse
fixture resets the cache after each admin test because a rolled-back savepoint would otherwise
leave the process cache ahead of the database.

### 3. Deactivation semantics

**Decision:** `FoodItem.is_active: bool = True` (a default is acceptable — it is not a safety
flag). `LoadedFoodTable.foods` and `resolve`/`matches` (and the resolution index) see active
entries only; `all_foods` (new) and `get(id)` see everything; `__len__`/`__contains__` count
active. `PROTECTED_FOOD_IDS = {breast_milk, infant_formula_iron_fortified}` cannot be
deactivated or moved out of `milk_feed`, and `milk_feed` is allowed only on those ids.
Deactivating an inactive food (or activating an active one) returns 200 and writes no
revision.

**Why:** The picker, the planner, and the chat tools must stop offering a withdrawn food, but
a feed logged last month must still price (`normalise_entry` uses `get`). The chat's
`log_feeding` can therefore still record an inactive food a parent actually gave — the log is
fact, not recommendation; recorded as a decision so it is not mistaken for a gap. The two
milk feeds are hard-wired in the feeding defaults and the planner's anchor, so removing them
would break both.

### 4. Validation split

**Decision:** Universal rules live on `FoodItem` (a model validator: `milk_feed` ⇒
`min_age_months == 0`; otherwise `>= SOLIDS_MIN_AGE_MONTHS = 6`) so the committed file, admin
writes, and imports obey the same rule. Admin-only rules live in `backend/nutrition/food_admin.py`
(protected ids; `milk_feed` reserved; `FoodWrite.source: str` required non-empty; import
`source` fill from the file-level source when a row omits it). Error text reuses `_describe`'s
`foods[i] (id).field` form so a form and an import report read the same.

**Why:** Hard rule 7 with each rule where its data is. `tests/test_nutrition_diet.py` builds a
`milk_feed` fixture named `formula`, so the "only two ids" rule cannot be universal.

### 5. Admin role and rate limit

**Decision:** `Settings.admin_emails: Annotated[list[str], NoDecode]` split, stripped,
lower-cased like `allowed_origins`; `is_admin(user, settings)`; `require_admin` → 403
`"Admin access required"`; `AdminUser = Annotated[User, Depends(require_admin)]`.
`CurrentUserResponse.is_admin` filled on register, login, and `me`. A separate `"admin"`
rate-limit bucket (`rate_limit_admin_per_minute`, default 30) on the four write routes.

**Why:** 403 not 404 — the refusal is a fact about the caller, not a probe into another
account's data, and `/api/admin` is public in the OpenAPI schema anyway. Sharing the `auth`
bucket (10/min) would lock an admin out of sign-in during an import session.

### 6. Routes and the import contract

**Decision:** `backend/api/admin_foods.py`, prefix `/admin/foods`, every route `AdminUser`:
`GET` → `{version, revision, source, foods: [FoodItem incl. is_active]}`; `POST` `FoodWrite` →
201 `{food, version, revision}` (409 duplicate id); `PUT /{food_id}` (body id must equal the
path, else 422; protected-id category change 409); `POST /{food_id}/deactivate|activate`
(404 unknown; 409 protected); `POST /import` `{format: yaml|csv, content ≤ 1 MiB, mode:
upsert|create_only = upsert, dry_run = false}` → 200 `{applied, created, updated, unchanged,
errors[{row, id, field, message}], version, revision}`; 422 only for an unparseable body or
format; 409 on a revision collision. YAML accepts a bare list or `{source?, foods: [...]}`;
CSV has a header of `FoodItem` field names, allergens `;`-separated, booleans `true`/`false`,
blank `source`/`notes` → null, optional `is_active`. Rows whose merged entry equals the
existing one are `unchanged`, and an import that changes nothing writes no revision.

**Why:** A JSON body keeps the "JSON-only bodies" CSRF posture and avoids `python-multipart`.
Returning the report with 200 and an `applied` flag keeps the frontend's error reader (which
expects a string detail) out of the per-row report.

### 7. Migration and seed

**Decision:** Revision `d4a9b3c4e004` (down `c3f8a2e2d003`): create the table, then seed
revision 1 by calling `load_food_table(<repo>/nutrition-data/foods.yaml)` (path from
`__file__`; the image copies both `alembic/` and `nutrition-data/`) and inserting
`table.table.model_dump(mode="json", exclude={"version"})` with summary "Seeded from
nutrition-data/foods.yaml <version>". `FoodItem` gains a `@field_serializer("allergens")`
emitting a sorted list so the seed and every snapshot are deterministic. Downgrade drops the
table. Category stays a code-level `FoodCategory` inside the JSONB, not a PostgreSQL enum.

**Why:** The seed should be the file as validated at the time the migration runs — a fresh
database with an invalid seed should fail at migration, not at first request. This is a
deliberate exception to the initial migration's "no live imports" rule and is stated in the
docstring. Adding a category remains a code change.

### 8. Frontend

**Decision:** `app/admin/foods/page.tsx` renders a gate on `useSession`: pending → loading,
signed out → the existing `AuthForm`, `!is_admin` → refusal card with a link back, admin →
`AdminFoodsPage`. `chat-page.tsx` header shows `ADMIN_LINK` when `user.is_admin`.
`hooks/use-admin-foods.ts` (`["admin", "foods"]`; mutations invalidate that key and
`["foods"]`); `["admin"]` joins the caches removed on sign-out and 401.
`lib/admin-food-form.ts` (pure, tested): every field a string, the four safety fields
`"yes" | "no" | ""` with `""` the untouched state, `toFoodWrite` mirrors the server rules.
`lib/enums.ts` gains `FoodCategory` + options and the enum fixture gains `food_category`.
Components in `components/admin/`: `food-table.tsx` (semantic `<table>`, inactive rows muted,
"show inactive" toggle), `food-form.tsx` (allergen checkboxes; safety radios as `Button
role="radio"` with nothing checked; 422/409 detail shown verbatim), `import-panel.tsx`
(`<input type="file">` read with `FileReader`, format from the extension, mode select, "Check
file" dry run → grouped results and an errors table → "Import" enabled only when the dry run
was clean).

**Why:** The API's 403 is the real gate; the page only avoids a broken screen. Nothing
preselected is what makes "explicit safety metadata" true in the UI.

### 9. Copy

**Decision:** Direct voice throughout; unambiguous safety labels: "Choking hazard for children
under 4 (AAP list)", "Contains honey", "Commonly served unpasteurized", "Earliest age, in
completed months" with the hint "0 only for breast milk and formula; every solid is 6 or
more"; "Answer yes or no for every safety question before saving"; "Deactivated foods leave
the picker and meal plans; feeds already logged with them keep their nutrients"; "Nothing was
imported; fix the rows below and check the file again"; "This page is for administrators of
the food table".

## Risks / Trade-offs

- [Two table origins] → prod raises if the database table cannot load; the version string
  names the origin (`db-N` vs the file's date); the fallback logs a warning.
- [Process cache vs rolled-back test transactions] → autouse cache reset in admin tests.
- [`FoodItem` validator tightening rejects a future fixture] → the message names the entry;
  the rule is what `test_only_milk_feeds_under_six_months` already asserts.
- [Migration imports application code] → a change to `FoodItem` that invalidates the file
  fails the fresh-database migration; `TestCommittedTable` catches it before commit.
- [Concurrent admins] → primary-key collision → 409; the page refetches.
- [Table growth] → 1 MiB import cap; the planner and resolver iterate active foods per
  request, fine into the low thousands.
- [`is_admin` widens the account read] → the authentication spec delta says exactly what is
  added; `test_api_auth.py` key-set assertions updated.

## Migration Plan

1. Apply backend and frontend together. Locally `uv run alembic upgrade head` seeds revision 1;
   run the suites.
2. Set `ADMIN_EMAILS` in `.env` locally and in Render (`sync: false`); deploy; the frontend
   ships in the same push.
3. Rollback: `alembic downgrade c3f8a2e2d003` drops the revisions table (admin edits since the
   seed are lost; the file is still the fallback); revert the commit.
