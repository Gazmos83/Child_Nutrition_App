## Context

See proposal.md — Why. Relevant current state:

- `backend/models/child_profile.py` stores `age_in_months` (SmallInteger, CHECK 0–60),
  `weight_kg Numeric(5,2)`, `height_cm Numeric(4,1) NULL`; `TimestampMixin` gives
  `created_at` only. One Alembic revision exists (`a1d6f0c0b001`); `tests/test_migrations.py`
  round-trips `downgrade base → upgrade head`.
- `backend/api/children.py` is the authority seam: `_apply()` maps `ChildProfileWrite` onto
  the model, `to_response()` and `to_child_context()` read it; `resolve_chat_request()` in
  `backend/api/chat.py` and `get_targets()` both build `ChildContext` from it. The chat
  router's `PROFILE_FIELDS` overwrite every model-proposed profile argument with the stored
  value, so `age_months` reaching the tools is whatever `to_child_context` says.
- `backend/models/feeding.py` + the `/feedings` routes are the pattern for a child-owned
  log: raw rows, nutrients priced on every read, `OwnedChild` on every route, 404-as-absence
  for other accounts, `ON DELETE CASCADE`.
- `backend/nutrition/growth.py:assess_growth(params, table)` is pure and cached via
  `backend/tools/nutrient_tools.py:assess_growth`; `GrowthAssessmentInput` takes
  `age_months, sex, weight_kg, height_cm=None`. `backend/nutrition/` has no LangChain import.
- `backend/chat/copy.py:GROWTH_NEEDS_HEIGHT` says "pop it in the side panel".
- Frontend: the Feeding log tab is the template — `hooks/use-feeding-log.ts` (query key,
  `setQueryData` on mutate, invalidate `dailyTargetsKey`), `side-panel/feeding-log-tab.tsx`,
  `side-panel/log-feed-form.tsx` (local `useMutation`, 422 detail shown verbatim),
  `lib/feeding-log-store.ts` (pure list helpers). The child form's `heightNeeded` derives
  from `form.age_months`; `lib/child-context-store.ts:toChildContext` validates it.
  `chat/growth-card.tsx` has a private `IndicatorRow` (label, band badge, percentile,
  `Progress` SD track, reference line, WHO term). `components/ui/` has no date picker.
  `lib/copy.ts` is the single copy source with a whole-module snapshot test that also
  fails on `!` and on prose literals in components.
- Evals: `evals/cases.yaml` children carry `age_months`; `evals/harness/client.py:save_child`
  posts them to `/api/children` unchanged.

## Goals / Non-Goals

**Goals:**
- Age stops going stale: one stored date of birth, one pure completed-months function,
  every consumer of `age_months` unchanged.
- A measurement log with the same shape and guarantees as the feeding log: raw rows,
  everything derived recomputed on read, owner-scoped, cascade-deleted.
- The Growth tab is built from the Feeding-log tab's parts and the growth card's row; no
  new dependency, no new UI primitive.
- The migration round-trips and backfills the dev database without manual steps.

**Non-Goals:**
- Anything under proposal.md — Non-goals (charts, edit/upsert, delete rollback, per-user
  timezone, seeding, daily WHO tables).
- Changing `GrowthAssessmentInput`/`GrowthAssessmentResult`, the chat SSE contract, or the
  router.

## Decisions

### 1. Store `birth_date`, drop `age_in_months`, derive age at read time

**Decision:** `child_profiles.birth_date DATE NOT NULL` replaces `age_in_months`. The model
gains `age_months_on(as_of: date) -> int` and a property `age_months` (as of the UTC date
today). `ChildProfileWrite.birth_date` replaces `age_months` (`extra="forbid"` rejects the
old field). `ChildProfileResponse` returns `birth_date` and the derived `age_months`.
`to_child_context()` fills `ChildContext.age_months` from the property, so `ChildContext`,
`PROFILE_FIELDS`, `general_targets`, prompts, and every tool are untouched.

**Why:** A birth date is an event; an age is a count of months from it — hard rule 1
governs the age, which stays an integer of months everywhere it is stored, returned, or
reasoned about. Keeping `age_in_months` beside `birth_date` would be a second source of
truth that is wrong within a month. Breaking the write API is deliberate: a stale client
posting `age_months` should 422 loudly rather than have a birth date guessed for it.

**Alternatives:** keep `age_in_months` and add a nullable `birth_date` — rejected (two
truths); accept both on write for compatibility — rejected (the frontend and evals are the
only clients and change in the same commit).

### 2. Completed-months arithmetic in `backend/nutrition/age.py`, stdlib only

**Decision:** New pure module with `today()` (the UTC date; the one definition of "today"),
`completed_months(birth_date, as_of)`, `birth_date_for(months, as_of)` (inverse, for tests
and the evals adapter), and `DATE_TOLERANCE = timedelta(days=1)`. Completed months =
calendar-month difference, minus one when `as_of.day` is before the birthday's day, with the
birthday clamped to the last day of `as_of`'s month when that month is shorter. `as_of <
birth_date` raises.

**Why:** Six lines of arithmetic; `python-dateutil` is not worth a dependency. The
clamping rule matches PostgreSQL's `date - interval 'N months'`, which the migration
backfill relies on, so the SQL and the Python agree. `backend/nutrition/` is where the
deterministic arithmetic lives and where the no-LangChain invariant is enforced.

**Tolerance:** "today" is the UTC date; a parent east of UTC is on tomorrow's date for part
of every day, so `birth_date` and `measured_on` are accepted up to `today() + 1 day`, and
the derived age is clamped at 0. A per-user timezone is the recorded [Stretch].

### 3. Validation split: Pydantic for the shape and today, the route for cross-table rules

**Decision:** `ChildProfileWrite` validates `birth_date <= today() + DATE_TOLERANCE` and
`completed_months(birth_date, today()) <= 60`; the height-required-from-36-months rule
uses the same derived age. `GrowthMeasurementWrite` validates the shape (weight `_WEIGHT`,
height `> 0, <= MAX_HEIGHT_CM`) and `measured_on <= today() + DATE_TOLERANCE`. The route
enforces what needs the stored child: `measured_on >= child.birth_date` (422 naming the
date of birth) and `child.age_months_on(measured_on) <= 60` (422; WHO tables stop at 60,
so every stored row stays assessable). The `(child_profile_id, measured_on)` unique
constraint turns a duplicate into an `IntegrityError` → rollback → 409.

**Aged-out profiles:** a stored child can pass 60 months over time. Reads of the profile
keep working (`age_months` is an unbounded int in the response). Building `ChildContext`
would raise a Pydantic error and 500, so `children.py` gains `child_context_or_422(profile)`
used by `get_targets` and `resolve_chat_request`; it answers 422 naming the supported range.

**Why:** Hard rule 7 (validate before use) with each rule where its data is: Pydantic can
see today, only the route can see the child. Letting the database catch the duplicate is
the same stance the feeding log takes on concurrent id collisions.

### 4. `GrowthMeasurement` table, one row per child per day

**Decision:** `growth_measurements`: UUIDv7 `id`, `child_profile_id` FK `ON DELETE
CASCADE`, `measured_on DATE NOT NULL`, `weight_kg Numeric(5,2) NOT NULL`, `height_cm
Numeric(4,1) NULL`, `created_at`; CHECKs `weight_kg > 0`, `height_cm IS NULL OR height_cm
> 0`; `UniqueConstraint(child_profile_id, measured_on, name="uq_growth_measurements_child_day")`
(explicit name; the convention would name it after the first column only). No separate
index on the FK — the unique constraint leads on it and is the list's ordering index.
Nothing derived is stored. `ChildProfile.growth_measurements` relationship mirrors
`feedings`.

**Why:** A calendar date, not a timestamp: growth is measured once, at the clinic or on the
bathroom scale, and a time of day would be invented. One-per-day defines "newest" without a
tie-break and makes the natural double submit a 409 instead of a duplicate. Fixed-point
columns match `weight_kg`/`height_cm` on the profile.

**Alternatives:** `measured_at TIMESTAMPTZ` like `fed_at` — rejected (fabricated precision,
ambiguous "same day"); allow several per day and take the latest `created_at` — rejected
(the parent then has two rows for one weigh-in with no way to tell which is right).

### 5. Assessment computed on read with the full existing result shape

**Decision:** `GET /children/{id}/growth` returns, newest first, rows of `{id, measured_on,
age_months, weight_kg, height_cm, assessment, created_at}` where `age_months =
child.age_months_on(measured_on)` and `assessment` is the unchanged `GrowthAssessmentResult`
from `nutrient_tools.assess_growth(GrowthAssessmentInput(...))`. `assessment` is `None`
(with a logged warning) only when a later `PUT` moved the birth date so a stored row now
falls outside 0–60 months — the row is still returned so the parent can see and delete it.

**Why:** Same stance as the feeding log (price from the table on every read; the table is
versioned and may improve). The frontend already has the TypeScript type and a row
component for exactly this shape, and a future chart plots the flat fields plus
`reference` from the nested result. Returning rather than skipping an unassessable row is
more honest here than in the feeding list because there is no "table no longer knows this
food" analogue — the row is the parent's own data.

### 6. Newest-by-date measurement writes through to the profile, in one transaction

**Decision:** `POST /children/{id}/growth` reads `max(measured_on)` for the child; if none
exists or `measured_on >=` it, the route sets `child.weight_kg` and, when `height_cm` is
supplied, `child.height_cm`, then commits row and profile together. A measurement without
height never clears the profile's height. `PUT /children/{id}` only writes `birth_date`
where it wrote `age_months`; it creates no row. `DELETE` of a measurement does not touch
the profile.

**Why:** User decision: the freshest numbers should feed targets and plans, and a parent
should not type the same weight twice. "Height absent" means "not measured today", not "no
height" — clearing it would also break the ≥36-months height rule on the profile. Rolling
back on delete would require picking the previous row's values, which may predate a form
edit; disclosed in the tab copy and left as [Stretch].

### 7. Server-generated ids; no idempotency key

**Decision:** The measurement id is generated server-side; `POST` accepts no `id`.

**Why:** The feeding log's client-supplied id exists because the chat's `log_feeding` tool
hands the browser an already-identified entry. No chat tool logs measurements, and the
per-day unique constraint already catches a double submit.

### 8. One migration, backfilled from `created_at`, exactly reversible

**Decision:** Revision `b2e7f1d1c002` (down `a1d6f0c0b001`), hand-written. Upgrade: add
`birth_date` nullable → `UPDATE … SET birth_date = ((created_at AT TIME ZONE 'UTC')::date -
make_interval(months => age_in_months))::date` → set NOT NULL → drop the age CHECK and
column → create `growth_measurements`. Downgrade: drop the table → add `age_in_months`
nullable → recompute it from `birth_date` and `created_at` with PostgreSQL `age()`, clamped
to 0–60 → NOT NULL → re-add the CHECK → drop `birth_date`. No seeded measurement rows.

**Why:** `created_at` (not `now()`) makes the backfill deterministic on any dump and is the
youngest birth date consistent with "N completed months when the profile was created". It
is off by up to a month for dev rows — acceptable for a dev database with no production
data; the parent corrects it once in the form. The clamp guarantees the restored CHECK can
be added. Dropping the CHECK explicitly keeps the file symmetric and the name visible.

### 9. Frontend: birth date as a native date input; derived months shown beside it

**Decision:** `ChildForm.birth_date: string` replaces `age_months`; `<Input type="date"
max={today}>` via the existing `Input` wrapper; a pure `completedMonths(birthDate, today)`
in `child-context-store.ts` (parse `YYYY-MM-DD` by parts, never `new Date(string)`) drives
both the "N months old" hint and the 36-months `heightNeeded` gate; `toChildContext`
reports `FORM_ERROR_BIRTH_DATE` for a malformed, future, or >60-months date. The save
mutation surfaces a 422 detail verbatim so a rare client/server month disagreement near a
birthday is explained rather than generic.

**Why:** The wire format is the input's native value; no new dependency; `fireEvent.change`
works in jsdom. The client-side months are a convenience; the server's derivation is the
authority (Decision 1).

### 10. Frontend: Growth tab assembled from existing parts

**Decision:** `hooks/use-growth-log.ts` (`growthKey(childId) = ["growth", childId]`; list
query; `add`/`remove` mutations that `setQueryData` the list then invalidate `CHILDREN_KEY`
and `dailyTargetsKey(childId)`), `lib/growth-log-store.ts` (newest-first insert/remove,
date formatting), `side-panel/log-measurement-form.tsx` (date defaulting to today, bounded
`min={birthDate} max={today}`; weight; optional height; client checks reuse
`FORM_ERROR_WEIGHT`/`FORM_ERROR_HEIGHT`; 422/409 detail shown verbatim),
`side-panel/growth-tab.tsx` (needs-child, unavailable, form + status line, empty state,
`<li>` per measurement with header line and one `GrowthIndicatorRow` per indicator, a
single note when `height_cm === null`, source line and `GROWTH_TREND_NOTE` once).
`growth-card.tsx` exports its `IndicatorRow` as `GrowthIndicatorRow` — the only change to
the card. `chat-page.tsx` adds the fourth trigger and content. `["growth"]` joins the
account-scoped caches removed on sign-out, 401, and profile clear.

**Why:** Mirrors the Feeding-log tab one-for-one so the structure is already tested and
familiar; the card's row is the reusable unit and its tests assert only on test ids and
copy, so exporting it is zero-risk. Rendering one local "no length or height with this
one" note instead of three backend skip reasons keeps the row short.

### 11. Copy: direct voice, one backend string reworded

**Decision:** New `GROWTH_*` and `FORM_BIRTH_DATE_*` strings in `copy.ts` (direct voice,
no `!`, disclosed profile effect: "the newest measurement also sets the weight and height
on the Child tab"); `FORM_AGE_*` removed; `FORM_CLEAR_CONFIRM` and the no-safe-plan
checklist mention the birth date and the growth log. `backend/chat/copy.py:GROWTH_NEEDS_HEIGHT`
drops "the side panel" and names the missing length or height only, so the same result
reads correctly in the chat card and in a growth-log row.

**Why:** Weight status is a direct-voice topic (Day 5 Decision 13); copy lives in one file
per side so the snapshot reviews every sentence.

### 12. Evals keep speaking in months

**Decision:** `evals/harness/client.py:save_child` pops `age_months` from a case and sets
`birth_date = birth_date_for(age_months, today()).isoformat()` before posting.

**Why:** Cases read better as "an 8-month-old" than as a date that means something
different every day; the harness is the one client that can translate.

## Risks / Trade-offs

- [UTC "today" vs the parent's local date] → one-day tolerance on writes; derived age
  clamped at 0; a client/server disagreement of one month near a birthday only affects the
  36-months height gate and comes back as a 422 shown verbatim. Per-user timezone is
  [Stretch].
- [Backfilled birth dates are approximate] → dev data only; accurate to within a month;
  the form shows the date so the parent corrects it once. No production rows exist.
- [A stored child ages past 60 months] → profile reads still work; context building answers
  422 naming the range; a `PUT` is refused by the write validator; a stored measurement that
  a birth-date edit pushes out of range is returned with `assessment: null`, not dropped.
- [Time-dependent tests] → compute `today()` once per test; keep the fixed-date scenario
  (born 2026-01-10, measured 2026-05-09/10) for the arithmetic; a run straddling UTC
  midnight could flake by a month — negligible, noted.
- [Unique-constraint name drift between model and migration] → the same literal in both;
  `uv run alembic revision --autogenerate` after applying should produce no operations.
- [Frontend `age_months` → `birth_date` rename misses a reference] → `pnpm typecheck` is
  the safety net; every stale reference fails to compile.
- [The exported row component drifts from the card] → the card keeps using it; its test
  covers both consumers indirectly.

## Migration Plan

1. Apply the backend and frontend changes in one change (the write API is breaking; the
   only clients are the frontend and the evals harness, both updated here).
2. Locally: `uv run alembic upgrade head` against the dev database (backfills eight
   profiles), then `uv run pytest` with `TEST_DATABASE_URL` set (includes the migration
   round-trip and the new backfill test).
3. Deploy: Render runs `alembic upgrade head` at start as today; the Vercel frontend ships
   in the same push so no client posts `age_months` against the new API.
4. Rollback: `uv run alembic downgrade a1d6f0c0b001` restores `age_in_months` (clamped) and
   drops the measurements table; revert the commit. Measurements entered in between are
   lost — acceptable for a [Stretch] feature with no production users yet.
