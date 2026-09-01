## Context

See `proposal.md` — Why. The constraints that shape the approach:

- A nutrient is not a thing in the codebase today; it is a name repeated in ~11 sites. Three
  band tables with *different* cut points (energy 3/6/12/35/60 months; protein and iron
  6/12/47/60), three heterogeneous result types, two closed `Literal` unions, per-nutrient
  `if/elif` chains in three modules, fixed-arity formatters in the frontend.
- The three nutrients are structurally unalike: calories is a formula (weight-derived below
  36 months, then a sex-specific equation needing height and an activity coefficient),
  protein is per-kilogram-of-bodyweight, iron is a flat per-band constant. Any uniform model
  must hold all three without collapsing into `Any`.
- `backend/tools/targets_resolution.py` documents itself as the single definition of "the
  child's daily targets", shared by the meal planner, `get_remaining_targets`, and
  `detect_nutrient_gaps`. That property must survive, not be worked around.
- `backend/tools/meal_plan.py` runs a greedy composer that balances a protein shortfall
  against an iron shortfall and caps iron at its upper limit. Its output is pinned
  byte-for-byte by a 15-case fixture. A standing project decision says not to reopen the
  band boundaries or the composer-vs-filter split.
- The knowledge base already publishes the DRI tables for zinc, calcium, vitamin D, B12 and
  more, and the AAP vegetarian/vegan guidance names exactly the nutrients needing attention.
  The values exist; only the plumbing is missing.
- ~466 backend tests, plus frontend tests with committed snapshots.

## Goals / Non-Goals

**Goals:**

- One declarative home for every reference intake figure, so adding a nutrient is one table
  row rather than an eleven-site diff.
- Delete the triplicated per-nutrient `if/elif` chains rather than adding a fourth.
- Keep the composer, its fixture, and the whole frontend compiling and behaving unchanged
  through the type reshape.
- Make the display-versus-track distinction structural, so an unobservable nutrient cannot
  acquire a flag by accident anywhere in the system.

**Non-Goals (design-level; see `proposal.md` — Non-goals for scope):**

- No change to how a calorie or protein target is *computed*. The equations keep their
  exact arithmetic and provenance strings; the energy equation's body moves into the
  registry module (Decision 1), while the public tool functions keep their homes,
  signatures, and result shapes.
- No new abstraction over the food table, the safety filter, or the diet filter.
- No attempt to make the estimated-energy-requirement equations declarative (Decision 1).
- No client-side computation of any nutrient figure.

## Decisions

### Decision 1 — A registry of typed derivations, with the energy equation kept as code

The registry holds one row per nutrient. The per-nutrient reference data is a closed tagged
union of derivation styles: flat per-band values (iron, zinc, calcium, vitamin D, B12),
per-kilogram values (protein), a named equation (calories), and an advisory carrying text
and no number (DHA). A single `match` over that union replaces the three ad-hoc lookups.

The energy case is a *named function living in the registry module* behind a typed
callable, rather than `88.5 − 61.9 × y + PA × (26.7 × kg + 903 × m) + 20` expressed as
table rows. The public tool function `calculate_calorie_target` stays in `targets.py` with
its signature and result shape unchanged, and delegates to the registry's equation.

- **Why the equation is code, not rows:** attempting to make it declarative is where
  uniform-model refactors die — it forces `Any`-typed lambdas and loses the provenance
  string the tool-activity display already shows. Two of the three styles genuinely are
  data; the third genuinely is code, and the design should say so rather than pretend
  otherwise.
- **Why the equation body lives in the registry module (amended during apply):** the
  dependency can only run one way. `targets.py` imports the registry's shapes and tables,
  and `schemas/tools.py` imports the registry's unit vocabulary, so the registry can import
  neither back to bind a callable defined elsewhere. The buildable arrangements were a
  function-local deferred import (hides a real dependency), a third module (adds a layer
  two files would share), or moving the equation beside the tables it belongs with. The
  last is also the most honest: the equation *is* reference data from the same DRI report.
  Verified behaviour-preserving by the full suite passing with zero test edits.
- **Alternative rejected:** a fully declarative formula DSL. More machinery than eight
  nutrients justify, and untypeable without erasing the distinction between the styles.
- **Alternative rejected:** leaving the three tables in place and adding a fourth for the new
  nutrients. That is the eleven-site tax paid again, and it is the status quo this change
  exists to end.

### Decision 2 — Reshape `NutrientTargets` to an ordered set behind a compatibility façade

`NutrientTargets` becomes an ordered collection of uniform target rows, plus three computed
properties that reconstruct today's `calories`, `protein` and `iron` members. Pydantic
serializes computed fields, so the emitted JSON is a **superset** of today's.

- **Why:** this is what makes a uniform model safe at this stage. The composer,
  `feeding_log.py`, `gaps.py`, `doctors_note.py`, the meal-plan card, the gap card and the
  frontend types all keep their existing view and need no edit in the same step that changes
  the shape. The riskiest file in the repo is untouched by the riskiest change.
- **Alternative rejected:** a parallel payload for the panel, leaving `NutrientTargets` at
  three. It keeps the diff smaller but creates two representations of "the child's targets"
  with no type-level relation, directly contradicting the single-definition property, and it
  would need a dedicated anti-drift test to stay honest. That test is worth having anyway
  (see Risks), but the duplication is not.
- **Alternative rejected:** a big-bang rewrite of every consumer in one step. It would
  regenerate the composer fixture in the same commit that reshapes the types, destroying the
  only evidence the composer did not move.
- **Consequence, accepted:** the façade is duplication with a fixed lifetime. It carries a
  dated marker and a task row, and it cannot drift because both views derive from the same
  ordered set. Removing it, and migrating the frontend to read the set directly, is named
  follow-up work rather than an implicit intention.

### Decision 3 — Trackability is data, so behaviour is a filter and never a branch

A registry row declares which food-table field supplies its intake, and for which diets that
field is actually reachable. "Tracked" is derived from that declaration, not asserted
separately. Gap detection iterates the trackable subset; a non-trackable row therefore cannot
reach it.

- **Why:** the alternative is `if nutrient == "vitamin_d"` scattered across gap detection,
  the endpoint and the renderer — three chances to forget one. Deriving it means vitamin D is
  absent from the flagged set by construction. Validation on the target row makes the
  invariant enforced rather than merely intended: a non-trackable row carrying an average,
  ratio or flag is rejected at the boundary, so the failure mode is a loud error rather than
  a wrong number on a parent's screen.
- **Alternative rejected:** a hand-maintained list of "nutrients we don't score". A second
  place to update, and it says nothing about *why*.

### Decision 4 — Vitamin B12 is display-only for vegan, tracked for vegetarian

This amends what was originally approved (tracking for every displayed nutrient) and is
recorded here so the narrowing is explicit rather than silent.

The food table has no fortified plant-milk or nutritional-yeast row, and the vegan diet
filter removes flesh, dairy and egg. A vegan child therefore has no loggable B12 source, so
a flag could only ever read `below`.

- **Why:** such a flag is not false so much as uninformative — it cannot distinguish a
  supplemented child (fine) from an unsupplemented one (the actual danger), which is the only
  distinction that matters clinically. The honest surface is the number plus the AAP
  supplement guidance, exactly as for vitamin D. Presenting a permanent red bar would also
  train parents to ignore the one nutrient the guidance is most emphatic about.
- **Alternative rejected:** track it anyway and let it read `below`. Produces a defect that
  looks like a parent-facing bug report, not a test failure.
- **Alternative rejected:** add a fortified plant-milk food row now to make it genuinely
  trackable. Reasonable, and the cleanest eventual answer, but it is food-table work with its
  own sourcing and belongs with the deferred zinc/B12 data task. Once such a row exists this
  decision reverses by changing one registry field.

### Decision 5 — Diet preference joins the target-input contract, defaulted

The shared target-input contract gains `diet_preference` with the vocabulary's default. Its
documented exclusion of diet ("the planner's, minus diet and allergies") is replaced with the
sharper invariant: *diet selects which targets are displayed and their order; it never
changes a number.*

- **Why:** defaulting means every existing construction across ~466 tests still validates, so
  this is additive rather than a breaking contract change. Placing diet on the contract rather
  than passing it beside the child keeps the two request schemas that extend that contract
  from needing a second, parallel way to carry it.
- **Why the invariant matters:** there is no vegan RDA for iron. The registry deliberately
  cannot express a per-diet value, which makes the guarantee structural rather than a
  convention someone could breach later.
- **Alternative rejected:** a separate `diet` argument threaded through the resolution
  functions. The two extending request schemas would then have nowhere to put it.

### Decision 6 — The targets read is deterministic and makes no language-model call

The endpoint returns the general reference targets. It does not run doctor's-note extraction.
The response states whether a note is on file, and the panel says the note is applied when
meal plans are generated.

- **Why:** the panel is persistent, so an extraction per profile load is a latency and cost
  cost paid on every visit, and it would make the panel's numbers non-reproducible across
  loads. It also keeps the panel working where the model provider is unconfigured, which
  matters for a UI element that is always on screen.
- **Hard rule 3 is honoured** by disclosure rather than by silence: the parent is told the
  note exists and where it takes effect, so nothing implies it was ignored.
- **Alternative rejected:** extract on every load. Cost and non-determinism for a number the
  meal planner already applies correctly.
- **Alternative rejected:** apply the note from a cache now. The right eventual answer — the
  note's recorded-at timestamp already exists as a cache key — but caching is its own
  correctness surface and is deferred rather than half-built.

### Decision 7 — Reported targets widen; the composed-against set does not

A plan reports the child's full displayed set and composes against calories, protein and
iron.

- **Why:** widening the report improves the audit record (hard rule 8) at no behavioural cost,
  because the composer reads three named values and cannot see the rest. Widening the
  composed-against set would turn a two-objective greedy fill into a five-objective one — a
  genuine algorithm redesign, against a standing decision, with upper-limit interactions per
  added nutrient.
- **Consequence:** the meal-plan card keeps showing coverage for three. That is consistent
  with what the composer aimed at, not an oversight, and the specs say so to stop a future
  reader "completing" it.

### Decision 8 — The composer's regression fixture is projected, not regenerated

Three keys in the 15-case fixture legitimately change shape. The assertion compares a
projection (the plan items, coverage and message whole; totals on their original keys; the
three targets whole through the façade) instead of the fixture being regenerated.

- **Why:** that fixture is the only byte-for-byte evidence the composer's output has not
  moved. Regenerating it inside the change that reshapes the types would discard the guard at
  exactly the moment it is most needed. Projection keeps it alive across the refactor.

### Decision 9 — The panel reflects the saved profile, never the unsaved form draft

The panel reads targets for the persisted profile. While the form holds unsaved edits it says
the details must be saved first, rather than showing numbers for a draft age.

- **Why:** the alternative implies the browser computed something, and computing targets
  client-side would breach the rule that no nutrient number a parent sees originates in the
  browser. Showing stale numbers beside an edited age is worse than showing none.

### Decision 10 — Per-nutrient labels and units come from the server

The renderer takes each row's label and unit from the payload rather than a local map.

- **Why:** the existing frontend label map is keyed to three nutrients and returns nothing
  for a fourth, so widening the tracked set without this renders blank labels for calcium.
  Sourcing labels from the payload removes a whole class of "add a nutrient, forget the
  label" defects. **Sequencing consequence:** the label change ships with the gap-detection
  widening, not after it.

## Risks / Trade-offs

- **Unit slips across newly introduced units** → three of the added nutrients use units the
  codebase has never carried (micrograms, international units). B12 is 0.9 µg not 0.9 mg;
  vitamin D is 600 IU not 15 µg; calcium is 700 mg at two years, not the infant 260 mg.
  Mitigation: a parity test asserting every registry value appears verbatim in the knowledge
  base, plus a mandatory printed sanity pass across ages and diets. Automated band tests
  alone would not catch a figure that is internally consistent but wrong.
- **The façade outliving its purpose** → two serialized views of the same target, one marked
  transitional, will start to look like the design if it survives two more changes.
  Mitigation: a dated marker in code and an explicit task row for its removal; it cannot
  drift meanwhile, since both views derive from one ordered set.
- **A "quiet" widening of the meal-plan payload** → plans now report nutrients the composer
  ignored, which a reader could mistake for a composition target. Mitigation: stated as a
  requirement in the specs, and asserted by a test that two plans differing only in the
  displayed set produce identical items.
- **The single-definition property weakening** → the panel and the planner both derive from
  the same resolution path, but the panel skips the note step by design (Decision 6).
  Mitigation: a test tying the panel's calorie figure to the resolved general target, and
  disclosure in the UI so the difference is never invisible to a parent.
- **Deferred zinc and B12 data leaves a visible asymmetry** → those two are displayed but
  unscored, for a reason that is a data gap rather than a nutritional one. Mitigation: each
  non-trackable row carries a parent-facing reason, so the asymmetry reads as an explanation
  rather than a gap in the product.
- **Trade-off accepted:** the change is larger than the feature strictly needs, because it
  pays down the eleven-site duplication instead of adding to it. The justification is that the
  nutrient count has just moved for the first time and the knowledge base already documents
  six more; the additive route pays the same tax again for each.

## Migration Plan

Staged so the test suite is green at the end of every stage, and so the two riskiest items
(food data, the composer) are isolated from the type reshape.

1. **Registry, additive.** New module; the protein and iron band tables move into it and are
   imported back, so the existing public tool functions stay byte-identical. New tests only.
2. **Uniform target row and the façade.** Reshape the collection; add the three computed
   properties. Every consumer keeps its current view. Fixture assertion switches to the
   projection (Decision 8) in this stage, before anything else can disturb it.
3. **Doctor's note onto the registry.** Delete both per-nutrient chains; derive the
   extraction prompt's nutrient list and the unit map from the registry so prompt and
   validation cannot drift. The overridable set stays three, asserted against the registry.
4. **Gap detection widens.** Iterate the trackable subset; calcium joins. Ship the
   server-supplied label change together with this stage (Decision 10).
5. **Endpoint.** The owner-scoped deterministic read.
6. **Frontend.** Types, query hook, panel component, copy, mount, cache invalidation on
   profile and feeding-log changes.
7. **Sanity pass.** Printed targets across ages and diets checked against the knowledge base;
   printed plan totals against the widened target set; the panel read as a parent for a vegan
   toddler.

**Rollback:** stages 1–2 are additive and independently revertible. From stage 4 onward the
observable change is the wider gap set and the new panel; reverting the endpoint and the
frontend leaves a working system with calcium additionally flagged. No schema migration and
no data backfill, so rollback is a code revert with nothing to undo in the database.
