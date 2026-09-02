## Context

See `proposal.md` — Why. The constraints that shape the approach:

- A food entry is a **Pydantic model, not a SQL table**. `FoodItem` is
  `frozen=True, extra="forbid"`, and the whole table is persisted as one JSONB snapshot
  per revision in `food_table_revisions`. Nutrients live inside that JSON, so adding a
  field needs no DDL — but every stored snapshot is **re-validated against the current
  `FoodItem` on every read**, so a new required field would break the loading of revision
  1 and everything after it.
- The committed seed, `nutrition-data/foods.yaml`, holds 57 entries. None carries a
  micronutrient value, and hard rule 5 forbids inventing one without provenance.
- The registry in `backend/nutrition/nutrients.py` is the single source of nutrient
  vocabulary and units. It names `vitamin_b12` and documents the exact field name it
  expects the food table to grow: `vitamin_b12_ug`. It also holds a zinc entry with
  reference bands, displayed unscored — which this change removes (Decision 3a).
- `tests/test_nutrition_nutrients.py` guards that every registry `intake_field` names a
  real attribute on both `NutrientTotals` and `FoodItem`. Adding attributes cannot break
  it; wiring an `intake_field` without adding the matching `NutrientTotals` field would.
- The admin form already renders its number fields from one array, so the JSX is generic.
  The string-to-value layer in `frontend/src/lib/admin-food-form.ts` is not: it has five
  hand-written lists that assume every number field is required.

## Goals / Non-Goals

**Goals:**

- Store seven micronutrients per food and let an administrator enter them.
- Remove zinc's target everywhere a parent or the chat model could see one.
- Keep every existing stored revision and the committed seed loading with no rewrite and
  no migration.
- Keep "not measured" distinguishable from a measured zero, at every layer.
- Use field names and units the registry already dictates, so the deferred tracking work
  needs no rename.

**Non-Goals** (design-level, on top of the proposal's Non-goals):

- No change to how any nutrient is *scored* or aggregated; no display change to any
  nutrient other than zinc's removal.
- No new abstraction for "optional nutrient". Seven declarations in the existing style
  beat a registry-driven form.

## Decisions

### Decision 1: Optional fields (`float | None = None`), not `0.0` defaults

New fields are `float | None = Field(default=None, ge=0)`. The six existing nutrients stay
required and unchanged.

*Why:* `None` is the only honest value. A default of `0.0` would assert that a pear
contains no zinc, which is a nutrition claim we have no source for — and it would be
indistinguishable from a curator who measured zero. That distinction is exactly what the
deferred tracking work will need to decide whether a total is complete.

*Alternatives considered:* (a) required fields plus a data migration rewriting revision 1's
JSONB and all 57 seed entries — rejected: it needs 399 invented numbers, violating hard
rule 5, and it breaks any revision an operator already created; (b) a separate
`micronutrients: dict[str, float]` sub-object — rejected: it loses per-field validation and
`extra="forbid"`, and it would not match the flat `intake_field` names the registry expects.

### Decision 2: Field names and units come from the registry

`zinc_mg`, `vitamin_a_ug`, `iodine_ug`, `vitamin_b12_ug`, `folate_ug`, `vitamin_c_mg`,
`fiber_g`. Calcium is untouched at `calcium_mg`.

*Why:* the registry's convention is `mg → _mg`, `g → _g`, `µg → _ug`, `kcal → bare`, and
its B12 comment names `vitamin_b12_ug` literally. Matching it now means the deferred B12
tracking change sets `intake_field` and nothing else. Units follow the DRI tables the
registry already cites: vitamin A in µg RAE, folate in µg DFE. `zinc_mg` follows the same
unit convention even though zinc leaves the registry (Decision 3a) — food field names are
not derived from `NutrientKey`.

### Decision 3a: Zinc's registry entry is deleted — storage without a target

The zinc `NutrientSpec` and the `"zinc"` member of `NutrientKey` are removed. Zinc keeps
no reference bands and no Daily Targets row for any age or diet; the `zinc_mg` food field
is its only remaining presence, exactly like `vitamin_a_ug` or `iodine_ug`.

*Why:* the user's explicit decision — "Treat Zinc as a micronutrient that gets storage but
no target", confirmed against the alternative of keeping the unscored row. Zinc could
already never produce a gap or deficiency (`intake_field=None` excludes it from scoring in
three independent ways: the `GapNutrient` literal, `tracked()` filtering, and the
`NutrientTarget` validator), so what is removed is the displayed reference amount and its
"we don't have zinc values yet" note, which dies with the spec.

*Alternatives considered:* keeping the unscored row (recommended to the user as the
zero-registry-change option; declined). Keeping the bands but hiding the row was not
considered seriously — an invisible target is dead data the parity test would still bind
to the knowledge base.

*Consequences:* `openspec/specs/child-profile/spec.md`'s displayed-set scenario names zinc
and needs a MODIFIED delta, and `openspec/specs/doctors-note-override/spec.md`'s
"contains six nutrients" scenario needs a MODIFIED delta with count-free wording. The priority sequence keeps a harmless gap at 50 (sorting is by
value). The knowledge-base document keeps its zinc prose — the registry-to-source parity
test binds registry entries to the document, not the reverse. The `zinc_mg` field name
stays correct: food field names follow the unit convention, and nothing derives them from
`NutrientKey`.

### Decision 3b: Vitamin B12 stays untracked, verbatim

B12's `intake_field` stays `None`, and its `not_tracked_reason`, diet gating, and advisory
notes stay exactly as written.

*Why:* wiring intake now would score every child against an all-zero intake and report a
false deficiency — worse for a parent than an unscored target, and squarely against "not a
medical device". Flipping it is a data-gated follow-up, and it needs `NutrientTotals`, the
feeding log, and gap detection to first answer "how does a total report partially measured
data", which is a real design question, not a one-line change. The user chose to leave the
copy as written.

*Consequence:* `deterministic-nutrient-tools` and `nutrient-gap-detection` specs need **no**
delta from this change — their statements about B12 not being trackable stay accurate, and
their unscored-row scenarios name vitamin D and B12, not zinc.

### Decision 4: A second, optional class of number field in the form layer

`admin-food-form.ts` gains `MICRONUTRIENT_FIELDS` alongside the existing
`NUMBER_FIELDS`, and validation loops over both with different empty-handling: blank is an
error for the required list, and `undefined` for the optional one. `fromFood` renders a
stored `null` as `""`.

*Why:* it keeps one code path per rule instead of a per-field conditional, and it keeps the
required six behaving exactly as they do today. The generic `.map()` in `food-form.tsx`
renders the new group from the new array with no new field-rendering code.

### Decision 5: Blank means not measured, `0` means zero — enforced at the string boundary

The form sends the key omitted (or `null`) for a blank field, never `0`. Import does the
same: `_csv_row` already skips blank cells for keys outside `("source", "notes")`, so
adding the seven names to `_NUMBER_FIELDS` gives blank-means-unknown for free, and a
non-numeric cell keeps failing its row with the field named.

*Why:* the distinction has to hold at the only place a blank exists — the string layer.
Below it there is no blank, just `None` or a number.

### Decision 6: A separate, labelled "optional" group in the form

The seven render in their own group after the required nutrients, under a heading and a
hint that blank means not measured.

*Why:* thirteen undifferentiated number inputs would read as thirteen required ones, and a
curator guessing a value to fill a box is the exact failure hard rule 5 exists to prevent.
The visual separation is what makes "leave it blank" the obvious action.

### Decision 7: No Alembic migration, and no values added to the seed

Decision 1 makes existing snapshots valid as-is, so there is nothing to migrate. The seed
file gains only a header comment documenting the new optional keys.

*Why:* a migration would exist solely to write values we do not have. The seed's 57 entries
stay at "not measured" until a sourced backfill happens, which is its own change.

## Risks / Trade-offs

- **The form grows to 13 number inputs and gets long.** → Decision 6's separate group plus
  the existing two-column grid; the seven are visibly optional, so the required path is no
  longer than today.
- **A curator reads a blank field as "zero" and the table quietly under-reports.** → The
  group hint says blank means not measured, and nothing consumes these values yet, so an
  under-reported blank cannot reach a parent during this change. Decision 3b's deferred
  B12 tracking work must handle partial data explicitly before it can.
- **Someone later sets `intake_field` for B12 without adding it to `NutrientTotals`.** →
  The existing registry guard test fails immediately and by name. Left as-is deliberately.
- **The zinc removal misses a hard-coded expectation.** → The reference sweep found every
  zinc mention; the failing-test list in tasks.md is exhaustive, and the full suites run
  against a recorded baseline so any missed assertion surfaces as a named new failure.
- **`ge=0` on an optional field is easy to drop by accident.** → The spec delta carries a
  negative-value scenario per surface (entry, form, import), so all three are tested.
- **Import files in the wild.** → No column becomes mandatory, and the "file without
  micronutrient columns" scenario pins that older files keep working.

## Migration Plan

None required. Deploy is a code deploy: no schema change, no data rewrite, and no
re-ingestion. Rollback is reverting the code — snapshots written while the new fields
existed carry extra keys, so a rollback would trip `extra="forbid"` on any revision created
after the deploy. Practically that means: if rolling back, also roll the served table back
to a revision created before the deploy, exactly as the food-table-admin smoke cleanup
already does.
