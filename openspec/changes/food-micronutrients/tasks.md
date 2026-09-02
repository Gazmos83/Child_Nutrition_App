Authorization note: every task below sits behind the existing `AdminUser` dependency on
`/api/admin/foods` (401 without a session, 403 without the `ADMIN_EMAILS` role). No task
adds, widens, or bypasses a route, and no task touches user-scoped data — the food table is
global, not per-user. Hard rule 9 is unaffected.

## 1. Food entry storage

- [x] 1.1 Add the seven optional fields to `FoodItem` in `backend/nutrition/foods.py` as
  `float | None = Field(default=None, ge=0)` — `zinc_mg`, `vitamin_a_ug`, `iodine_ug`,
  `vitamin_b12_ug`, `folate_ug`, `vitamin_c_mg`, `fiber_g` (design Decisions 1 and 2), in
  that order after `calcium_mg`. Verify `uv run pytest tests/test_nutrition_foods.py`
  passes with no fixture edits, proving the existing required-only entries still validate.
- [x] 1.2 Add tests to `tests/test_nutrition_foods.py`: an entry with some micronutrients
  set round-trips them; an omitted one reads back as `None`; an explicit `0` reads back as
  `0.0` and not `None`; a negative value fails validation naming the field. Verify all four
  pass.
- [x] 1.3 Confirm the seed and every stored revision still load: run
  `uv run pytest tests/test_migrations.py -m db` and
  `uv run python -c "from backend.nutrition.foods import load_food_table; print(len(load_food_table('nutrition-data/foods.yaml').table.foods))"`
  and verify it prints 57.
- [x] 1.4 Document the seven optional keys in the header comment block of
  `nutrition-data/foods.yaml`, stating that absent means not measured and that a value
  needs its own source. Add no values to the 57 entries (design Decision 7). Verify
  `git diff --stat nutrition-data/foods.yaml` shows comment lines only.

## 2. Admin write and bulk import

- [x] 2.1 Add the seven field names to `_NUMBER_FIELDS` in
  `backend/nutrition/food_admin.py` so CSV cells coerce to numbers and blank cells stay
  absent (design Decision 5). Verify `uv run pytest tests/test_food_admin.py` passes.
- [x] 2.2 Extend `CSV_HEADER` in `tests/test_food_admin.py` with the seven columns and add
  cases: a file with micronutrient columns imports the filled cells and leaves blank cells
  unmeasured; a file with none of the new columns imports unchanged; a row with `-2` for
  zinc fails naming the row and the field with nothing written. Verify they pass.
- [x] 2.3 Extend `CSV_HEADER` and the `PEAR` payload in `tests/test_api_admin_foods.py`,
  and add API cases: a create carrying three micronutrients returns 201 and the GET reports
  those three plus `null` for the rest; a create with a negative iodine value returns 422
  naming the field and writes no revision. Verify
  `uv run pytest tests/test_api_admin_foods.py -m db` passes.
- [x] 2.4 Update the `parse_import` docstring in `backend/nutrition/food_admin.py` to say
  micronutrient columns are optional and a blank cell means not measured. Verify
  `uv run ruff check backend tests` and `uv run ruff format --check backend tests` are
  clean.
- [x] 2.5 Confirm no schema drift: run `uv run alembic upgrade head` then
  `uv run alembic revision --autogenerate -m drift-check` and verify the generated
  revision has an empty `upgrade()`, then delete the generated file.

## 3. Frontend types and copy

- [x] 3.1 Add the seven optional fields to `FoodItem` in `frontend/src/lib/api-types.ts`
  as `number | null`, mirroring the backend order. Touch nothing else in that file — the
  user has uncommitted `DailyTargetsResponse` work in it. Verify
  `git diff frontend/src/lib/api-types.ts` shows only the food block plus their existing
  hunk.
- [x] 3.2 Add to `frontend/src/lib/copy.ts`: `ADMIN_FIELD_ZINC` ("Zinc (mg)"),
  `ADMIN_FIELD_VITAMIN_A` ("Vitamin A (µg)"), `ADMIN_FIELD_IODINE` ("Iodine (µg)"),
  `ADMIN_FIELD_VITAMIN_B12` ("Vitamin B12 (µg)"), `ADMIN_FIELD_FOLATE` ("Folate (µg)"),
  `ADMIN_FIELD_VITAMIN_C` ("Vitamin C (mg)"), `ADMIN_FIELD_FIBER` ("Fiber (g)"), plus a
  group heading and a hint that these are optional and blank means not measured. Follow the
  existing `ADMIN_FIELD_*` "Name (unit)" style and add them next to the current nutrient
  labels. Keep every edit off the user's `TARGETS_*` lines.
- [x] 3.3 Re-record the copy snapshot with `pnpm -C frontend vitest run copy` and verify
  the only added snapshot lines are the new `ADMIN_FIELD_*` keys plus the heading and hint,
  with the user's existing `TARGETS_*` snapshot hunk left intact.

## 4. Admin form

- [x] 4.1 In `frontend/src/lib/admin-food-form.ts`, add the seven keys to `FoodForm`,
  export `MICRONUTRIENT_FIELDS`, and extend `emptyFoodForm()` (each `""`) and `fromFood()`
  (stored `null` renders `""`, a number renders `String(value)`) — design Decision 4.
- [x] 4.2 In the same file, validate the optional fields in `toFoodWrite`: blank is
  accepted and omitted from the payload, a non-negative number is sent, and anything else
  sets `ADMIN_ERROR_NON_NEGATIVE` on that field. Leave the required six loop unchanged.
- [x] 4.3 Add cases to `frontend/src/lib/__tests__/admin-food-form.test.ts`: an all-blank
  micronutrient form validates and its payload omits the seven keys; a filled one sends the
  numbers; `"0"` sends `0` rather than omitting; `"-1"` in iodine and `"abc"` in folate
  each produce a field error. Verify
  `pnpm -C frontend vitest run admin-food-form` passes.
- [x] 4.4 In `frontend/src/components/admin/food-form.tsx`, add a `MICRONUTRIENT_LABELS`
  array pairing each key with its copy label and render it as a separate group after the
  existing nutrient grid, with the heading and optional-hint copy (design Decision 6),
  reusing the existing `Field` + numeric `Input` pattern.
- [x] 4.5 Add cases to `frontend/src/components/admin/__tests__/food-form.test.tsx`: the
  seven labelled inputs render; saving without touching them succeeds and omits them;
  filling zinc and vitamin C sends those two; opening a food that stores zinc but not
  folate shows the zinc value and a blank folate. Verify
  `pnpm -C frontend vitest run food-form` passes.

## 5. Zinc target removal (design Decision 3a)

- [x] 5.1 In `backend/nutrition/nutrients.py`, delete `"zinc"` from the `NutrientKey`
  literal and delete the zinc `NutrientSpec` from `REGISTRY`. Verify
  `uv run pytest tests/test_nutrition_nutrients.py -q` fails only in the known zinc tests
  (band boundaries, display order, knowledge-base parity parametrization, key/literal
  match), confirming no unexpected coupling.
- [x] 5.2 Update `tests/test_nutrition_nutrients.py`: delete `TestBandBoundaries.test_zinc`
  and remove `"zinc"` from all seven expected tuples in
  `TestDisplayOrder.test_membership_and_order`. Verify the file's suite passes, including
  the `intake_field` guard and the `not_tracked_reason` check.
- [x] 5.3 Update `tests/test_tools_targets_resolution.py`: drop zinc from the expected
  order in `test_infant_omnivore_set_order_and_figures` and switch
  `test_unscored_rows_carry_a_reason` from `targets.require("zinc")` to vitamin D, which
  stays permanently unscored. Verify the file's suite passes.
- [x] 5.4 Update `tests/test_api_children.py` (`test_owner_reads_the_ordered_set_with_disclaimer`
  exact key order; `test_logged_days_put_flags_on_tracked_rows_only` loops vitamin D only)
  and `tests/test_tools_doctors_note.py` (`len(general.items) == 5` and its comment).
  Verify both files pass with `-m db` where required.
- [x] 5.5 Update `frontend/src/components/side-panel/__tests__/daily-targets.test.tsx`:
  remove the zinc `targetRow` fixture line, change "six rows in server order" to five, and
  fix the tracked-rows comment. Touch nothing else in the file — the user's WIP failures
  (missing `overrides` in fixtures) stay theirs. Verify
  `pnpm vitest run daily-targets` (from `frontend/`) shows at most the six pre-existing
  failures and no new ones.
- [x] 5.6 Confirm zinc appears nowhere reachable: `grep -rn zinc backend/` returns only the
  `zinc_mg` food field, and `grep -rn zinc frontend/src --include='*.ts' --include='*.tsx'`
  returns only the admin field label and form code. Knowledge-base and eval prose zinc
  mentions stay (corpus content, not registry-bound).
- [x] 5.7 Add the `doctors-note-override` delta spec: its "An overridable nutrient still
  applies normally" scenario says the displayed set "contains six nutrients" (now five);
  reword count-free. Verify `openspec validate food-micronutrients --type change --strict`.

## 6. Verification

- [x] 6.1 Run the full backend suite `uv run pytest` and compare against the recorded
  baseline (1138 passed, 37 deselected): no failures; the count drops by 9 for the deleted
  zinc tests (8 band-boundary cases plus zinc's knowledge-base parity parametrization) and
  rises by the new food/import tests. Watch the meal-plan regression fixtures and
  `tests/test_nutrition_nutrients.py`'s `intake_field` guard.
- [x] 6.2 From `frontend/`, run `pnpm vitest run`, `pnpm lint`, and `pnpm typecheck`.
  Baseline is 6 failed / 164 passed, all in daily-targets, plus WIP typecheck errors.
  Verify every remaining failure names a `daily-targets` path and none names a food file.
- [x] 6.3 Verify against a live server, signed in as an `ADMIN_EMAILS` account: create a
  food with three micronutrients filled and four blank, reopen it and confirm the three
  show and the four are blank, edit one blank to `0` and confirm it reads back as `0`, and
  confirm a negative value is refused with the field named. Confirm the served table
  version advanced by one revision per successful write.
- [x] 6.4 Confirm the parent-facing surface: the food picker exposes no micronutrients, a
  meal plan's nutrient totals are unchanged, the Daily Targets tab shows **no zinc row**
  for a saved child, and vitamin D and vitamin B12 still show unscored with their existing
  notes verbatim (design Decisions 3a/3b).
- [x] 6.5 Run `openspec validate food-micronutrients --type change --strict` and confirm it
  passes.
- [x] 6.6 Delete the smoke foods and revisions created in 6.3, and confirm the served table
  is back to the revision it started at.
