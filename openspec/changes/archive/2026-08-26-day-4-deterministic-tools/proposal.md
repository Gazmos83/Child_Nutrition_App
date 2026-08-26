## Why

Days 1–3 built the data model and a grounded question-answering pipeline, but nothing yet
turns a child's profile into a number. Every nutrient figure the assistant states today
is a sentence quoted from a guideline document — correct for "how much iron does an
8-month-old need," useless for "how much iron does *my* 8-month-old need," which requires
arithmetic over that specific child's age and weight. The architecture principle is
explicit that this arithmetic must never come from the LLM: "the LLM extracts structured
inputs; it never generates nutrient numbers itself — all quantities come from a
lookup-table-driven Python function." Day 4 builds that function, and the guardrails
around it: a meal plan is not just a number, it is a recommendation a parent will act on,
so it must pass a safety filter the LLM cannot talk its way around (hard rule 4), and it
must defer to a clinician's written guidance rather than overrule it silently (hard rule
3).

**Scope: [MVP]. Day 4 of 7.**

## What Changes

- **Curated food-composition data** — a small lookup table of common infant/toddler foods
  (~30–50 items), each carrying nutrient values per serving (calories, protein, iron,
  and the other figures the meal planner needs) and safety metadata: which of the "big
  nine" allergens it contains, whether it is a choking hazard, whether it contains honey,
  whether it is commonly served unpasteurized, and the minimum age in months it is
  appropriate for. Sourced from the same USDA/NIH figures already cited in Day 3's
  knowledge base, so a nutrient number quoted in an answer and a nutrient number used in
  a meal plan trace to the same authority.
- **Deterministic nutrient-target functions** — `calculate_bmi()`, `calculate_calorie_target()`,
  and `calculate_protein_target()`, implementing the NIH DRI formulas already cited in
  `knowledge-base/nih-dri-energy-and-protein.md`. Pure Python, no LLM call, no database
  read. Every tool takes a validated Pydantic input (age in months, weight, height,
  sex, diet preference, allergies) rather than reading a stored profile — matching Day
  3's `/api/ask` precedent of staying unauthenticated and stateless until Day 6 ships
  auth (hard rule 9). `calculate_bmi()` takes height as a call parameter; it is not added
  to the `ChildProfile` schema this week (see Non-goals).
- **`lookup_food()` and `calculate_meal_nutrition()`** — deterministic lookups and
  summation against the food-composition data; no arithmetic performed by the model.
- **Hard-coded infant-safety filter** — a pure-Python module with no dependency on the
  RAG pipeline or the LLM, checking every candidate food against the child's age and
  recorded allergies: no honey under 12 months, no recognized choking hazards for
  children under 4, no commonly-unpasteurized products, no allergen the child is
  recorded against. Runs on every meal plan unconditionally; nothing bypasses it (hard
  rule 4).
- **Doctor's-note structured override** — when a profile carries a doctor's note, an
  LLM call (via the same OpenRouter chat model Day 3 wired up) extracts it into a
  validated, bounded structure (nutrient, direction, value, unit); extraction failure
  degrades to "no override, flagged as unparsed" rather than blocking the plan, mirroring
  Day 3's query-translation failure handling. Applying the override — deciding whether it
  conflicts with the general target and which value wins — is deterministic code, not
  the LLM (hard rule 3): the note always wins on conflict, and the conflict is returned
  as an explicit field, never silently blended.
- **`generate_meal_plan()`** — the core child-facing tool. Composes a nutrient target,
  candidate foods filtered by diet preference and allergens, the doctor's-note override,
  and the infant-safety filter into a plan, with the not-medical-advice disclaimer
  attached (hard rule "not a medical device").
- **Auditability logging** — every `generate_meal_plan()` call emits one structured log
  record carrying the full input snapshot (age, weight, height, sex, diet preference,
  allergies, doctor's note, rule/source used) per hard rule 8. Persisted to a queryable
  Postgres audit table only once Day 1's group 7 lands a live database (see Non-goals);
  today it is a structured log line, consistent with how Day 2's ingestion and Day 3's
  retrieval already log for operators.
- **LangChain tool wrappers** — each function above is also exposed as a LangChain
  `StructuredTool` with a typed schema, ready for Day 5's router to bind to the model.
  Day 4 does not wire them into a router or a chat endpoint; that is Day 5's "lightweight
  routing" work.

## Capabilities

### New Capabilities

- `food-composition-data`: a curated, versioned lookup table of common infant/toddler
  foods with per-serving nutrients and safety metadata, loaded and validated at process
  start the way Day 2's knowledge-base manifest is.
- `deterministic-nutrient-tools`: `calculate_bmi`, `calculate_calorie_target`,
  `calculate_protein_target`, `lookup_food`, `calculate_meal_nutrition` — pure functions,
  Pydantic-validated input and output, no model call, no persistence.
- `infant-safety-filter`: the hard-coded, RAG/LLM-independent safety check every
  candidate food and every generated meal plan passes through.
- `doctors-note-override`: LLM-assisted structured extraction of a doctor's note into a
  bounded override, and the deterministic logic that applies it and reports conflicts.
- `meal-plan-generation`: `generate_meal_plan()`, the core tool composing all of the
  above into one child-facing recommendation, with its audit log and disclaimer.

### Modified Capabilities

None. `child-profile` (Day 1) is read but not changed — see the height-field decision in
Non-goals.

## Impact

- **New code**: `backend/nutrition/` (food data loader, target formulas, safety filter),
  `backend/tools/` (the six tool functions, their LangChain wrappers, doctor's-note
  extraction), `backend/schemas/tools.py` (Pydantic input/output models),
  `nutrition-data/foods.yaml` (the curated food table), `tests/test_nutrition_*.py`,
  `tests/test_tools_*.py`.
- **Modified code**: none in `backend/models/`, `backend/api/`, or `backend/rag/`. No
  new API route and no change to `api_router`'s surface — Day 4 ships backend
  capabilities and LangChain-callable tools, not a new endpoint (Day 5 wires tools into
  the router/chat surface).
- **New data**: `nutrition-data/foods.yaml`, committed, following the same
  hand-curated + manifest pattern as `knowledge-base/`.
- **Dependencies**: none new — LangChain's `StructuredTool` and the OpenRouter chat
  model are already dependencies from Day 3.
- **No breaking changes** to Day 1's schema or Day 3's `/api/ask`.

## Non-goals

Deliberately deferred, per this session's scoping decisions:

- **`height_cm` on `ChildProfile`** — not added this week. `calculate_bmi()` takes
  height as a call parameter instead of a stored field, avoiding a new Alembic migration
  while Day 1 group 7 (Postgres integration) is still open. Revisit once a live
  database exists and it's clear whether height belongs on the profile or stays
  per-calculation.
- **`get_daily_nutrition()` and `get_remaining_targets()`** — both need a meals /
  meal-items log that does not exist yet. Deferred until meal logging is scoped
  (likely alongside Day 5's UI, which is the first place a parent would log a meal).
- **Router / chat integration** — Day 5. Day 4 produces tools; nothing calls them from
  `/api/ask` or any other endpoint yet.
- **Persisted, queryable audit table** — the hard rule 8 log exists as a structured log
  line this week; a Postgres table with a retrieval API waits for a live database
  (Day 1 group 7) and, if user-scoped, for auth (Day 6).
- **Growth-percentile lookups** (weight-for-age, BMI-for-age against WHO/CDC curves) —
  `calculate_bmi()` returns the BMI value only, not a percentile. Percentile lookups are
  a distinct, larger lookup-table problem (age- and sex-specific curves); candidate for a
  later day if evaluation shows it's needed.
- **AI-safety boundary handling** for the *conversational* surface (emergency symptoms,
  eating-disorder requests, medication interactions) — Day 6, as already scoped for
  Day 3. Day 4's disclaimer and safety filter cover meal-plan content specifically.
