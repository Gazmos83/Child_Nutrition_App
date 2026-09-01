## 1. Nutrient registry (additive)

- [x] 1.1 Replace the untyped band lookup in `backend/nutrition/targets.py` with a typed
  `band_for(bands, age_months) -> Band` helper and delete the two `# type: ignore[arg-type]`
  comments it forced; verify `uv run pytest tests/test_nutrition_targets.py` passes and
  `uv run ruff check` is clean
- [x] 1.2 Create `backend/nutrition/nutrients.py` with the `Band`/`NutrientSpec` shapes and
  the closed derivation union (flat per-band, per-kilogram, named equation, advisory) per
  design Decision 1; verify `uv run python -c "import backend.nutrition.nutrients"` succeeds
- [x] 1.3 Populate the registry rows for calories, protein and iron by moving
  `_PROTEIN_BANDS` and `_IRON_BANDS` out of `targets.py` and importing them back, with the
  calorie row wrapping the existing `calculate_calorie_target`; verify the full
  `uv run pytest` suite still passes with no test edits, proving the public tool functions
  are byte-identical
- [x] 1.4 Add the registry rows for vitamin D, zinc, calcium, B12 and the DHA advisory, with
  values, reference types, upper limits and sources taken verbatim from
  `knowledge-base/nih-dri-micronutrients.md` and `knowledge-base/aap-vegetarian-and-vegan-diets.md`
- [x] 1.5 Implement `displayed_specs(age_months, diet)` and the single `match`-based
  `evaluate()` dispatch; verify a new `tests/test_nutrition_nutrients.py` covers band
  boundaries at 6/7, 12/13, 47/48 and 60 months for every nutrient
- [x] 1.6 Add the knowledge-base parity test asserting every registry band value appears
  verbatim in `knowledge-base/nih-dri-micronutrients.md` (handling the thousands separator in
  `1,000 mg`); verify it fails when a value is deliberately altered
- [x] 1.7 Add registry invariant tests: every declared intake field is a real attribute of
  both the totals and food-item models; the overridable set equals the doctor's-note union;
  advisory rows are never trackable; keys unique; bands terminate at the maximum supported age

> **Deviation from 1.3, accepted 2026-09-01:** the 1.6 parity test surfaced that the old iron
> tool rounded the 0–6-month AI value to 0.3 mg; the published figure is 0.27 mg. The tool now
> returns 0.27 as published (hard rule 5), so the public output is *not* byte-identical for
> that one value: six fixture values in `tests/fixtures/meal_plans_before_change_2.json` and
> one expectation in `tests/test_nutrition_targets.py` were hand-corrected (see the
> `TestChangeTwoRegression` docstring; items, servings and messages verified byte-identical).
>
> **Design Decision 4 narrowing, recorded:** B12 is untracked for vegetarian as well as vegan
> until the food table gains `vitamin_b12_ug` — the deterministic-nutrient-tools delta spec's
> "no score yet" scenario is authoritative over the decision's headline.

## 2. Uniform target model and compatibility façade

- [x] 2.1 Add the uniform target row to `backend/schemas/tools.py` with its validators —
  exactly one of amount or advisory, a tracked row must have a numeric amount, a
  non-trackable row may not carry an average, ratio or flag; verify a new
  `tests/test_schemas_targets.py` rejects each violation
- [x] 2.2 Reshape `NutrientTargets` to the ordered set plus the three computed properties
  reconstructing `calories`/`protein`/`iron` (design Decision 2), and widen the unit union
  with micrograms and international units
- [x] 2.3 Rewrite `general_targets` in `backend/tools/targets_resolution.py` to delegate to
  the registry, and update its module docstring to state the ordered-set relationship; verify
  `uv run pytest` passes with **no edits** to `meal_plan.py`, `feeding_log.py`, `gaps.py` or
  `doctors_note.py`
- [x] 2.4 Switch the 15-case composer fixture assertion in `tests/test_tools_meal_plan.py` to
  the projection described in design Decision 8, and add a comment recording why the fixture
  is not regenerated; verify all 15 cases still pass without touching
  `tests/fixtures/meal_plans_before_change_2.json`
- [x] 2.5 Add the anti-drift test asserting the general calorie target from the registry
  equals the resolved target, both with and without a doctor's-note override

## 3. Doctor's note onto the registry

- [x] 3.1 Replace the two per-nutrient chains in `backend/tools/doctors_note.py` with keyed
  access and a single-nutrient replacement on the ordered set; verify
  `uv run pytest tests/test_tools_doctors_note.py` passes
- [x] 3.2 Derive the extraction prompt's nutrient list and the unit map from the registry's
  overridable rows so prompt and validation cannot drift; verify a test asserts the prompt
  text names exactly the overridable nutrients
- [x] 3.3 Add the tests for the new spec requirement: a note naming calcium is rejected and
  flagged as not applied even though calcium is displayed, and the overridable set stays
  exactly calories/protein/iron when the displayed set widens

## 4. Gap detection widens

- [x] 4.1 Extract the window-selection block in `backend/nutrition/gaps.py` into a reusable
  function with no behaviour change; verify `uv run pytest tests/test_nutrition_gaps.py`
  passes unchanged
- [x] 4.2 Replace the nutrient tuple and the per-nutrient target chain with iteration over
  the registry's trackable subset, reading each row's declared intake field; verify calcium
  now appears in gap reports and the existing three are unchanged
- [x] 4.3 Add tests for the new spec requirements: vitamin D never appears in a flagged set
  at any confidence; a vegan child's B12 is absent rather than reported below; switching a
  profile from vegetarian to vegan removes B12 and changes nothing else
- [x] 4.4 Change the gap and coverage renderers to take each row's label and unit from the
  payload rather than the local three-key map (design Decision 10 — must ship with 4.2);
  verify `pnpm -C frontend test` shows no blank label for calcium

## 5. Targets endpoint

- [x] 5.1 Add `GET /api/children/{child_id}/targets` to `backend/api/children.py` behind the
  existing `OwnedChild` dependency, reusing the child-context conversion. **Authorization
  boundary: the route resolves the profile only through the signed-in account's ownership
  dependency; a non-owner receives the same refusal as a direct profile read and no target
  value, age or diet preference is disclosed (hard rule 9).**
- [x] 5.2 Return the ordered target set plus the diet preference, a flag stating whether a
  doctor's note is on file, and the not-medical-advice disclaimer; make no language-model
  call (design Decision 6); verify the response is byte-identical across two calls
- [x] 5.3 Add the route to the user-scoped path list in `tests/test_app.py` so it is
  automatically covered by the unauthenticated-refusal test; verify that test passes
- [x] 5.4 Add API tests: owner receives 200; **a second account requesting the first
  account's child receives the same refusal as a direct read**; an unauthenticated request is
  refused; a vegan profile's response contains B12 and the DHA advisory; a profile with no
  logged days returns targets with no flags

## 6. Side panel

- [x] 6.1 Add the target row and response types to `frontend/src/lib/api-types.ts`, keeping
  the three legacy members while the façade lives; verify `pnpm -C frontend typecheck` passes
- [x] 6.2 Add the copy entries for the panel title, the saved-profile hint, the note-on-file
  disclosure and the display-only reasons; verify `pnpm -C frontend test -u` and review the
  copy snapshot diff line by line rather than accepting it wholesale
- [x] 6.3 Add `frontend/src/hooks/use-daily-targets.ts` keyed on the saved child id, and
  invalidate it from the existing profile-save, profile-clear and feeding-log mutations;
  verify a test asserts the query refetches after a profile save
- [x] 6.4 Add `frontend/src/components/side-panel/daily-targets.tsx` rendering rows in server
  order: tracked rows with a progress indicator and flag, display-only rows with their reason
  and **no** progress indicator, advisory rows as text with source and publication date
- [x] 6.5 Mount the panel under the child form in `frontend/src/app/chat-page.tsx`, showing
  the save-first hint while the form holds unsaved edits (design Decision 9)
- [x] 6.6 Add `daily-targets.test.tsx` covering: 9-month omnivore has six rows and no B12;
  30-month vegan shows B12 with no progress track and a DHA advisory with no value; vitamin D
  shows its reason; no saved child shows the explanation and no numbers; exactly one progress
  track per tracked row

## 7. Verification

- [x] 7.1 Run the full gate — `uv run pytest`, `uv run ruff check`,
  `pnpm -C frontend typecheck`, `pnpm -C frontend lint`, `pnpm -C frontend test` — and confirm
  all pass
- [x] 7.2 Run `openspec validate day-9-age-diet-aware-targets --strict` and confirm it passes
- [x] 7.3 Print the target set for 3, 9, 18, 30 and 48 months across omnivore, vegetarian and
  vegan, and check every value line by line against
  `knowledge-base/nih-dri-micronutrients.md`. Confirm specifically: calcium 700 mg at 24
  months (not the infant 260 mg), B12 in micrograms (0.9 µg, not mg), vitamin D in
  international units (600 IU, not 15 µg), iron ahead of protein at 9 months. Automated tests
  will not catch a figure that is internally consistent but wrong
- [x] 7.4 Print a generated meal plan's totals against the widened target set for 9, 24 and
  48 months and confirm no nutrient sits at an implausible fraction of target, which would
  indicate wrong food data rather than a wrong child
- [x] 7.5 Run the app (`uv run uvicorn` and `pnpm -C frontend dev`), open the child tab for a
  vegan 30-month-old, and read the B12 and DHA guidance as a parent would; confirm the
  note-on-file disclosure appears for a profile carrying a doctor's note
- [x] 7.6 Confirm the deliberately-unchanged list holds: no diff in the composer's algorithm,
  `NutrientCoverage`, the meal-plan card's coverage rows, `today-summary.tsx`,
  `RemainingNutrients`, the safety filter, the diet filter, or `nutrition-data/foods.yaml`
