## Why

The app computes daily nutrient targets for exactly three nutrients — calories, protein,
iron — and "three" is hardcoded independently in about eleven places: three ad-hoc band
tables in `backend/nutrition/targets.py`, three named heterogeneous fields on
`NutrientTargets`, two closed `Literal` unions, per-nutrient `if/elif` chains in
`gaps.py` and `doctors_note.py`, and fixed-arity formatters in the frontend. Adding one
nutrient today means editing all eleven.

That is also a nutritional gap, not only a structural one. The nutrients that matter most
shift sharply with age — iron needs jump at 7–12 months as birth stores are exhausted
(`knowledge-base/nih-dri-micronutrients.md`) — and with diet: every vegan child needs a
B12 source, and vitamin D needs a supplement across the whole age range
(`knowledge-base/aap-vegetarian-and-vegan-diets.md`). Those DRI values and diet rules are
already written up in the knowledge base and therefore already cited by the RAG pipeline,
but the app never turns them into a number for *this* child.

Scope: **[MVP]**. This is a **Day 9** change — an extension beyond the original 7-day plan,
following Day 8 (chat UX) and sharing its front-end surface.

## What Changes

- **A single declarative nutrient registry** (`backend/nutrition/nutrients.py`) becomes the
  only place a DRI figure appears, replacing the three independent band tables. Each row
  carries key, label, unit, derivation style, DRI bands with reference type (AI/RDA/EER)
  and upper limits, source citation, whether a food-log field supplies its intake, whether
  a doctor's note may override it, and its display priority rules.
- **Targets become an ordered, uniform, iterable set selected by age and diet preference.**
  Displayed always: calories, protein, iron, vitamin D, zinc, calcium. Added for vegan and
  vegetarian: vitamin B12. Added for vegan: an omega-3 DHA advisory carrying guidance text
  and no number.
- **A tracked/display-only distinction, derived from data rather than branched on.** A
  nutrient is tracked only if the feeding log can observe its intake. Vitamin D is
  display-only always (intake is supplements and sun); vitamin B12 is display-only for vegan
  (the food table has no fortified plant-milk or nutritional-yeast row, and the vegan filter
  removes flesh, dairy and egg, so a flag could only ever read `below` — which cannot
  distinguish a supplemented child from an unsupplemented one, the only distinction that
  matters). Gap detection widens to include **calcium**, whose per-food values already exist.
- **`NutrientTargets` is reshaped to `items` plus three computed properties** that
  reconstruct `calories`/`protein`/`iron`. Because Pydantic serializes computed fields, the
  emitted JSON stays a superset of today's, so `meal_plan.py`, `feeding_log.py`, `gaps.py`,
  `doctors_note.py` and the entire frontend keep compiling and behaving as they do now. Not
  a breaking change.
- **A new deterministic read**, `GET /api/children/{child_id}/targets`, behind the existing
  owner-scoped dependency. It calls no language model: a persistent panel must not fire a
  doctor's-note extraction on every load, and its numbers must be reproducible.
- **`diet_preference` is added, defaulted, to the target-input contract.** Diet selects
  which targets are displayed and their order; it never changes a number, because there is
  no per-diet DRI value.
- **A new persistent side-panel section** showing the child's daily targets in priority
  order, with reference type, band and source; display-only rows show their reason and no
  progress bar; advisory rows show text with source and publication date.

## Capabilities

### New Capabilities

None. Every behaviour introduced here belongs to an existing capability.

### Modified Capabilities

- `deterministic-nutrient-tools`: a single declarative registry is the only home of a DRI
  figure; targets are computed for an age- and diet-selected nutrient set; each target
  declares its reference type, band, upper limit, source, and whether intake is trackable.
- `nutrient-gap-detection`: the tracked set is the registry's trackable set rather than a
  fixed three (adding calcium); a nutrient whose intake the feeding log cannot observe is
  never flagged.
- `meal-plan-generation`: the targets a plan *reports* widen to the child's displayed set,
  while the set the composer *optimises toward* remains calories, protein and iron —
  stated explicitly so the distinction is not later "fixed".
- `doctors-note-override`: the overridable nutrient set remains exactly calories, protein
  and iron, and is explicitly independent of the displayed set.
- `child-profile`: diet preference selects which nutrient targets are displayed and their
  order; the targets read is reachable only through the owning account.
- `chat-ui`: the side panel shows the child's daily targets, priority-ordered, with
  display-only rows and advisories distinguishable from tracked rows.

## Impact

**Backend.** New `backend/nutrition/nutrients.py`. Modified: `backend/nutrition/targets.py`
(band tables move out; the EER equations stay put and stay authoritative),
`backend/nutrition/gaps.py` (per-nutrient chain deleted; loop over the tracked set),
`backend/tools/doctors_note.py` (two chains deleted; prompt nutrient list and
`UNIT_FOR_NUTRIENT` derived from the registry so they cannot drift from validation),
`backend/tools/targets_resolution.py`, `backend/schemas/tools.py` (uniform `NutrientTarget`,
reshaped `NutrientTargets`, widened `NutrientUnit` and `GapNutrient`),
`backend/api/children.py` (one new route).

**Frontend.** New `hooks/use-daily-targets.ts` and
`components/side-panel/daily-targets.tsx`; modified `lib/api-types.ts`, `lib/copy.ts`,
`app/chat-page.tsx`. Gap-report labels must come from the payload rather than the local
`COVERAGE_LABELS` map, sequenced with the gap-detection widening so no nutrient renders a
blank label.

**Unchanged, deliberately.** The composer's algorithm and optimisation set, the age-band
boundaries, `NutrientCoverage`, the meal-plan card's coverage rows, `today-summary.tsx`,
`RemainingNutrients` and `get_remaining_targets`, and the infant-safety and diet filters.

**Data.** No change to `nutrition-data/foods.yaml` in this change. No new dependencies, no
schema migration — the read is derived from the existing profile and feeding log.

## Non-goals

- **[Stretch] Zinc and vitamin B12 *tracking*.** Requires two new per-food fields sourced
  from USDA FoodData Central across all 57 rows of `nutrition-data/foods.yaml`, plus a
  `food-composition-data` requirement change. Deferred to a follow-up; both nutrients are
  *displayed* here, and enabling tracking later is one field per registry row. This is the
  only genuinely risky part of the wider feature and it is deliberately isolated.
- **[Stretch] Doctor's-note-aware panel numbers.** The panel shows general DRI targets and
  reports that a note is on file; applying the note there needs a cached extraction keyed on
  the existing `doctors_note_recorded_at`.
- **[Stretch] Nutrients beyond the focused core** (vitamin A, vitamin C, folate, iodine,
  potassium, sodium) — the registry makes each a one-row addition, but they are not in this
  change.
- **[Stretch] Removing the computed-property façade** and migrating the frontend to read
  `items[]` directly, including `meal-plan-card.tsx` coverage rows and `today-summary.tsx`.
  Tracked as named debt, not left implicit.
- **Widening what a doctor's note may override**, or adding a per-diet DRI value. Both are
  explicitly rejected, not merely deferred.
