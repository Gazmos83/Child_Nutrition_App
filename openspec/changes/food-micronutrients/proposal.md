## Why

An administrator curating the food table today can record only calories, protein, fat,
carbohydrate, iron, and calcium, so the micronutrients that matter most in the first four
years (zinc for growth, B12 for vegan and vegetarian children, iodine, folate, vitamin A,
vitamin C, fiber) cannot be captured at all.

This change adds the storage and the data-entry surface. It deliberately stops there: it
does **not** turn the new values into scored targets, because the table holds no data for
them yet and a scored target with no intake data would report every child as deficient.

It also carries one decided feature removal. Zinc currently has reference-intake bands in
the nutrient registry and shows in the Daily Targets tab as an unscored row. The user's
decision: zinc becomes a stored, editable per-food value with **no target anywhere** —
like vitamin A and iodine — so its registry entry is deleted and its Daily Targets row
disappears. Zinc can already never produce a deficiency today; this removes the displayed
reference amount as well. Vitamin B12 is untouched and keeps its unscored row and notes
verbatim.

Scope: **[Stretch]** — extends the [Stretch] `food-table-admin` capability. Belongs to the
post-Day-7 polish line, after the Day 7 deploy work.

## What Changes

- Seven new optional per-serving nutrient fields on a food entry: `zinc_mg`,
  `vitamin_a_ug`, `iodine_ug`, `vitamin_b12_ug`, `folate_ug`, `vitamin_c_mg`, `fiber_g`.
  Calcium is already stored as `calcium_mg` and needs no work.
- The new fields are **optional and default to "not measured"**, distinct from zero. The
  six existing nutrients stay required. This keeps the 57 committed foods, and every
  already-stored table revision, loading unchanged — a required field would make each of
  them fail re-validation on the next read.
- The administrator's "Edit Food" form gains the seven fields in a clearly separated
  micronutrients group. A blank field saves as "not measured"; a `0` saves as a measured
  zero. Any value given must still be a non-negative number.
- YAML and CSV bulk import accept the seven new columns, with a blank cell meaning "not
  measured". Files written against the old column set keep importing unchanged.
- Reading a food back reports the new values, `null` where not measured.
- **Zinc's nutrient target is removed** (decided feature removal, not breaking for data):
  the zinc entry leaves the nutrient registry, so the Daily Targets tab no longer shows a
  zinc row for any age or diet, and no tool result carries a zinc target. Zinc keeps no
  reference amount anywhere; it is storage-only, exactly like vitamin A and iodine. No
  stored data is affected — zinc never had intake, gaps, or overrides.
- Otherwise not a breaking change: no field is removed, renamed, or made stricter, and no
  stored data needs rewriting.

## Capabilities

### New Capabilities

None. This extends two existing capabilities.

### Modified Capabilities

- `food-composition-data`: the requirement fixing what every food entry carries is
  widened — the six current nutrients remain mandatory, and seven micronutrients become
  optional recorded values with "not measured" distinguished from zero.
- `food-table-admin`: the create/edit requirement and the bulk-import requirement are
  widened to cover the seven optional micronutrient fields, including blank-means-unknown
  handling and backward-compatible import files.
- `child-profile`: the displayed-target-set requirement's scenario names zinc in the base
  set; zinc leaves that set.
- `doctors-note-override`: one scenario says the displayed set "contains six nutrients",
  which is now five; the wording becomes count-free so no future registry change re-breaks
  it. The overridable set itself is untouched.

## Impact

**Backend**

- `backend/nutrition/foods.py` — seven fields on `FoodItem`. `FoodWrite` inherits them,
  so `backend/nutrition/food_admin.py` needs only the CSV number-field list extended.
- `backend/api/admin_foods.py`, `backend/schemas/admin.py` — no change; both are
  structural over `FoodItem`/`FoodWrite`.
- `nutrition-data/foods.yaml` — header comment documents the new optional keys. No values
  are invented for the 57 existing entries.
- **No Alembic migration.** Nutrients live inside the `food_table_revisions` JSONB
  snapshot, and optional fields let existing snapshots re-validate as-is.
- `backend/nutrition/nutrients.py` — the zinc `NutrientSpec` and the `"zinc"` member of
  `NutrientKey` are deleted. Nothing else names zinc: it was never in `GapNutrient`,
  `NutrientTotals`, the planner's composed set, or the prompts.
- Untouched by design: `NutrientTotals`, `backend/nutrition/feeding.py`,
  `backend/nutrition/gaps.py`, `backend/tools/*`. Feeding-log totals and meal nutrition
  keep summing exactly the six nutrients they sum today.

**Frontend**

- `frontend/src/lib/api-types.ts` — `FoodItem` gains the seven optional fields.
- `frontend/src/lib/admin-food-form.ts` — form shape, empty form, `fromFood`, validation,
  and `toFoodWrite` learn a second, optional class of number field.
- `frontend/src/components/admin/food-form.tsx` — a micronutrients group after the
  existing nutrients.
- `frontend/src/lib/copy.ts` — seven `ADMIN_FIELD_*` labels with units, plus a group
  heading and an "optional / leave blank if unknown" hint. Re-records the `copy` snapshot.

**Tests**

Food fixtures and both hard-coded CSV headers in `tests/test_food_admin.py` and
`tests/test_api_admin_foods.py`; the frontend food-form tests; the `copy` snapshot. The
existing guard in `tests/test_nutrition_nutrients.py` that every registry `intake_field`
names a real `FoodItem` attribute keeps passing untouched. The zinc removal deletes or
trims the tests that pinned zinc's bands, its place in the displayed set, and its unscored
row: `tests/test_nutrition_nutrients.py`, `tests/test_tools_targets_resolution.py`,
`tests/test_api_children.py`, `tests/test_tools_doctors_note.py`, and the frontend
daily-targets fixture.

## Non-goals

Deliberately deferred, each its own follow-up:

- **Making vitamin B12 a scored target.** Its registry `intake_field` stays `None` and its
  `not_tracked_reason` and advisory copy stay as written. With no values in the table,
  wiring intake would score every child at zero intake and report a false deficiency —
  worse than showing the target unscored. This becomes a real change once the table
  carries data, and it will also need `NutrientTotals`, the feeding log, and gap detection
  to handle "some foods measured, some not".
- **Any zinc target, ever, under this change.** Zinc is storage-only by decision, not
  deferred. Reintroducing a zinc target would be a new proposal.
- **Reference-intake bands for vitamin A, iodine, folate, vitamin C, and fiber.** These
  five have no `NutrientKey` entry or `NutrientSpec` today. Storing a value does not
  create a target; adding bands needs sourced DRI figures and a decision on how many
  nutrients the Daily Targets tab should show.
- **Backfilling the 57 existing foods.** Every number in this table ships with its
  provenance (hard rule 5). Values must come from a citable source (USDA FoodData Central
  primary; Open Food Facts and national tables secondary), not be guessed, so the backfill
  is a sourced data task, not part of this change.
- **Summing micronutrients into meal nutrition or feeding-log totals.** Requires deciding
  how a total reports "partially measured".
- **Showing micronutrients in the parent-facing food picker or on the admin list rows.**
  The picker intentionally exposes no nutrients.
