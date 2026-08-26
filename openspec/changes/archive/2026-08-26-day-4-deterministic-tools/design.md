## Context

See proposal.md — Why. The state this design starts from:

- `backend/models/enums.py` holds `Sex`, `DietPreference`, `Allergen` as `StrEnum`s mirrored
  by PostgreSQL enum types. They are the controlled vocabularies (hard rule 2) and are
  reused as-is; nothing in this change adds a database column or enum member.
- `backend/rag/prompts.py` owns `DISCLAIMER`, the fixed not-medical-advice text the
  meal-plan spec requires to match. `backend/rag/llm.py` owns `build_chat_model()` — the
  OpenRouter `ChatOpenAI` at temperature 0 — and the Day 3 retriever shows the pattern for
  a bounded LLM extraction: send a prompt, parse JSON out of the reply tolerating code
  fences, and on any exception or unparseable reply degrade with a warning rather than
  raise (`AdvancedRetriever.translate`).
- `backend/knowledge/loaders.py` shows the manifest pattern: a YAML file validated by a
  Pydantic model with `extra="forbid"`, duplicate keys rejected, and any invalid entry
  failing the whole load with an error naming the path.
- `knowledge-base/nih-dri-energy-and-protein.md` and `nih-dri-micronutrients.md` carry the
  exact figures the target functions implement: EER equations by age band (0–3, 4–6, 7–12,
  13–35 months weight-only; 3–8 years by sex with height and a physical-activity
  coefficient), protein per kg (1.52 AI, 1.2, 1.05, 0.95 g/kg), and iron (0.27 mg AI, 11,
  7, 10 mg). `aap-choking-prevention-2010.md`, `cdc-honey-and-infant-botulism.md`, and
  `cdc-food-safety-unpasteurized-and-storage.md` name the foods the safety flags mark.
- `tests/fixtures/fake_llm.py` provides `RecordingChatModel` (scripted replies, records
  prompts, can be told to fail) — sufficient to unit-test note extraction offline.
- Baseline: 288 tests pass, `ruff check .` clean.
- Day 5 will bind these tools to a router and render "tool activity"; the tool schemas
  and result shapes fixed here are that contract.

## Goals / Non-Goals

**Goals:**

- Every number a parent sees from these tools is traceable to a row in `foods.yaml` or a
  formula in the DRI document, and the same input always yields the same output.
- The safety filter is a pure function with no parameter that disables any rule, and the
  meal planner re-checks its own output against it before returning — two independent
  places a violation would have to slip past.
- Offline unit tests for everything, including note extraction (fake chat model) and the
  audit log (`caplog`).
- Result models carry enough structure (which source produced each target, what was
  excluded and why, whether a conflict occurred) for Day 5 to display and Day 6 to audit.

**Non-Goals:**

- Nutritional optimisation (linear programming over the food table). The planner is a
  deterministic greedy composition — a lookup-and-sum, not a solver.
- Doctor's-note guidance that is not a numeric nutrient target (e.g. "avoid dairy",
  "see a dietitian"). Extraction is limited to nutrient / direction / value / unit; other
  guidance is reported as not applied, never silently dropped.
- Portion-size personalisation beyond servings of the table's fixed serving sizes.
- Persisting anything. No database read or write occurs in this change.

## Decisions

### 1. Package layout: `backend/nutrition/` (data + rules) and `backend/tools/` (callables)

**Decision:** `backend/nutrition/foods.py` (table models + loader), `targets.py` (DRI
formulas), `safety.py` (infant-safety filter), `diet.py` (diet-preference exclusions).
`backend/tools/nutrient_tools.py` (the five pure tools), `doctors_note.py` (extraction +
override application), `meal_plan.py` (`generate_meal_plan`), `langchain_tools.py`
(`StructuredTool` wrappers). `backend/schemas/tools.py` holds every Pydantic input/output
model. Data lives in `nutrition-data/foods.yaml`.

**Why:** `nutrition/` has no LangChain import and no model dependency — it is the layer
hard rule 4 says must be independent of RAG/LLM, and keeping it in its own package makes
that independence a grep (`grep -r langchain backend/nutrition` is empty). `tools/` is
what Day 5 binds.

**Alternative considered:** one `backend/tools/` package for everything. Rejected — the
safety filter would then live beside the code that calls the LLM, and the independence
claim would be a convention rather than a package boundary.

### 2. Food table as validated YAML, loaded once per process, failing whole

**Decision:** `nutrition-data/foods.yaml` is a `FoodTable` (`version`, `source`,
`foods: list[FoodItem]`). `FoodItem` has `extra="forbid"`, required `id`, `name`,
`category`, `serving_size`, `serving_unit`, `calories`, `protein_g`, `fat_g`,
`carbohydrate_g`, `iron_mg`, `calcium_mg`, `allergens: set[Allergen]`, `choking_hazard`,
`contains_honey`, `commonly_unpasteurized`, `min_age_months` (0–60), optional `source`
override and `notes`. Nutrients are `>= 0`. Duplicate ids fail the load. `load_food_table
(path)` raises `ValueError` naming the file and entry on any problem; `get_food_table()`
is `lru_cache`d for the process, with `reset_food_table_cache()` for tests.

**Why:** Mirrors `load_manifest`. A partially valid table is worse than none: a food
missing its `contains_honey` flag would be *admitted* to infant plans.

**Category vocabulary** (`FoodCategory` StrEnum, module-local, not a DB enum): `milk_feed`
(breast milk, infant formula), `dairy`, `egg`, `meat`, `poultry`, `fish`, `shellfish`,
`legume`, `grain`, `vegetable`, `fruit`, `nut_seed`, `fat_oil`, `sweetener`. Diet filtering
(Decision 6) keys off it.

**Provenance:** Table-level `source` is USDA FoodData Central; entries whose figures come
from elsewhere (breast milk, formula — label/literature values) say so in their own
`source`. Figures are rounded typical values for the stated serving and are labelled as
such in the file header. The table stays at ~40 foods: enough for a varied plan at every
age band, small enough to hand-check.

**Alternative considered:** loading from the knowledge-base corpus itself. Rejected — the
corpus is prose for retrieval; nutrient arithmetic needs typed columns.

### 3. Age bands are inclusive in completed months, as the DRI tables write them

**Decision:** Energy bands: 0–3, 4–6, 7–12, 13–35, 36–60 months. Protein and iron bands:
0–6, 7–12, 13–47 ("1–3 years"), 48–60 ("4–8 years"). "1–3 years" starts at 13 months, not
12, matching the energy table's explicit "13–35 months" in the same source. Every target
result names its band and source string.

**Why:** The source tables are written in completed months/years with inclusive ends;
adopting one boundary convention across all three nutrients avoids a 12-month-old getting
"7–12 month" calories and "1–3 year" protein from the same call.

**Alternative considered:** first-birthday boundary (12 months → year-1 band). Rejected
because it contradicts the energy table's own boundary and would need a per-nutrient
exception.

### 4. Calorie target: EER equations verbatim; height and activity only where the equation needs them

**Decision:** For age ≤ 35 months, `EER = 89 × weight − 100 + growth_constant`. For
36–60 months, the 3–8-years equation by sex with height in metres and a physical-activity
coefficient; `height_cm` is therefore **required when age ≥ 36 months** and rejected at
validation with a message saying why. `ActivityLevel` (`sedentary`, `low_active`,
`active`, `very_active`) maps to the published PA coefficients per sex; default
`low_active`. Result rounded to a whole kcal.

**Why:** The DRI document says calculated values "should be produced from the equations
with the child's actual measurements rather than read from a general table." Defaulting
activity to `low_active` is the middle of the published range and is recorded in the
result (`activity_level`) so it is never hidden.

**Alternative considered:** age-band midpoint table (no height needed). Rejected — the
source says not to.

### 5. Protein and iron targets: per-kg for protein, fixed RDA/AI for iron

**Decision:** `protein_g = round(weight_kg × g_per_kg(band), 1)`. Iron is a fixed daily
value per band (the DRI gives no per-kg figure). The meal plan carries all three as
`NutrientTargets` (calories, protein_g, iron_mg), each with its source and band.

**Why:** Iron is the nutrient the knowledge base flags most often for 6–24 months and is a
required column on every food, so a plan that reports iron coverage costs nothing extra
and is what "nutrient-specific meal plan" in CLAUDE.md's MVP list means in practice.

### 6. Diet preference is a category exclusion, separate from the safety filter

**Decision:** `backend/nutrition/diet.py`: `vegan` excludes `dairy`, `egg`, `meat`,
`poultry`, `fish`, `shellfish`, and any `contains_honey` food; `vegetarian` excludes
`meat`, `poultry`, `fish`, `shellfish`; `pescatarian` excludes `meat`, `poultry`;
`omnivore` excludes nothing. `milk_feed` is never excluded by preference (breast milk and
infant formula are the sole food under 6 months and the DGA's required drink under 12).

**Why:** Preference is a household choice; safety is not. Keeping them in separate
functions means the safety filter's rule set is exactly the four hard-rule-4 checks plus
minimum age, and nothing else can be mistaken for it.

### 7. Safety filter: five rules, no switches, applied twice

**Decision:** `check_food(food, age_months, allergens) -> list[SafetyViolation]` applies:
`contains_honey and age < 12`; `choking_hazard and age < 48`; `commonly_unpasteurized`
(always); `allergens ∩ child allergens`; `age < food.min_age_months`. `filter_foods`
partitions candidates into eligible and `Exclusion(food_id, reasons)`. `assert_plan_safe
(items, age, allergens)` raises `UnsafePlanError` if any planned item has a violation.
The function signatures have no flag, environment variable, or setting that changes a
threshold; the thresholds are module constants. `generate_meal_plan` calls `filter_foods`
before composition and `assert_plan_safe` after.

**Why:** Hard rule 4 says the filter cannot be bypassed. The cheapest way to make that true
is to give it no inputs that could bypass it, and to check the output as well as the input
so a future composition bug cannot leak an unfiltered food.

**Alternative considered:** a single pre-filter. Rejected — one bug in the planner between
filter and return would be enough to break the rule.

### 8. Doctor's note: bounded extraction, deterministic application, 5 % tolerance

**Decision:** `DoctorsNoteOverride` is `nutrient ∈ {calories, protein, iron}`,
`direction ∈ {max, min, target}`, `value > 0`, `unit` fixed per nutrient (`kcal`, `g`,
`mg`) and validated to match. `extract_override(note, chat_model)` prompts for a single
JSON object or `null` (no numeric nutrient target present), parses with the Day 3
code-fence-tolerant approach, validates, and returns `NoteExtraction(status, override,
detail)` with `status ∈ {not_present, applied, no_numeric_target, unparsed}`. Any
exception, missing model, or validation failure → `unparsed` with a warning logged and
the note text untouched. `apply_override(targets, override, tolerance=0.05)` is pure
Python: `max` conflicts when the general value exceeds it, `min` when below, `target`
when they differ by more than 5 % relative; on conflict the note's value replaces the
general one and `OverrideOutcome(conflict=True, source="doctors_note", general_value,
applied_value)` is returned. Within tolerance or no violation → general value kept,
`conflict=False`, override still recorded.

**Why:** Hard rule 3 forbids blending, so the only two outcomes are "note wins" or "no
conflict". The tolerance stops a note saying "about 800 kcal" from being reported as a
conflict against a computed 790. Limiting to three nutrients is what makes the structure
bounded; a nutrient outside the set fails validation and is reported, never passed
through.

**Alternative considered:** letting the model decide whether there is a conflict.
Rejected by the spec ("SHALL NOT compare … using the language model").

### 9. Meal composition: milk anchor under 12 months, then greedy by iron density

**Decision:** Eligible foods come from Decisions 6 and 7. Under 6 months only `milk_feed`
foods are eligible (every solid has `min_age_months ≥ 6`), so the plan is milk servings to
meet the calorie target. From 6–11 months the plan first adds milk feeds covering half the
calorie target (WHO: milk remains a major energy source through 6–23 months; DGA: human
milk or formula is the drink under 12 months), then composes solids. From 12 months
`milk_feed` is dropped and `dairy` (whole cow's milk from 12 months) takes that slot via
the ordinary composition. Solids composition: one food from each of a fixed category order
(`grain`, `vegetable`, `fruit`, one of `legume/meat/poultry/fish/egg`, `dairy`), choosing
the eligible food with the highest iron per serving (tie → lowest id); then, while
calories < 90 % of target and items < 8, close the larger of the remaining protein and
iron shortfalls (as a fraction of target) with the *smallest* eligible serving that closes
it — or the largest contributor if none can — so overshoot is bounded to one serving;
once both targets are met, add the most calorie-dense food not yet in the plan instead, so
the top-up brings variety rather than more iron. No serving may push calories past 110 %
or iron past the DRI tolerable upper intake level (40 mg/day for 0–13 years). The composer never *recommends* a sweetener or a food on the
choking-hazard list, even at an age where the safety filter permits it (a planner
preference grounded in the DGA added-sugar limits and the AAP list; the filter's own rule
set is unchanged and still runs on the result). When both
milk feeds are eligible the anchor is breast milk (WHO recommends breastfeeding; a parent
using formula swaps it in Day 5's UI), with iron-fortified formula as the fallback. Items are assigned to
`breakfast`/`lunch`/`dinner`/`snack` round-robin. Servings may be fractional in 0.5 steps
only for the milk anchor; solids are whole servings. Totals come from
`calculate_meal_nutrition` over the plan.

**Why:** Deterministic, explainable ("chosen for iron"), and grounded: iron is the
nutrient the guidelines single out for 6–24 months, and category coverage is the DGA's
food-group pattern. A solver would be more precise and far harder to audit in a day.

**Alternative considered:** fixed template plans per age band. Rejected — they cannot
honour allergies and preference without a large template matrix.

### 10. `generate_meal_plan` is async; the pure tools are sync

**Decision:** `generate_meal_plan(request, chat_model | None)` is a coroutine because note
extraction awaits the chat model (as Day 3 does). `calculate_bmi`, `calculate_calorie_target`,
`calculate_protein_target`, `lookup_food`, `calculate_meal_nutrition` are plain functions.
`langchain_tools.build_tools(chat_model)` returns six `StructuredTool`s: the five pure
ones via `func=`, the planner via `coroutine=` only. With `chat_model=None`, a note is
reported `unparsed` ("extraction unavailable") and the plan still generates.

**Why:** FastAPI and the Day 5 router are async; forcing the planner sync would need
`asyncio.run` inside a running loop. Giving the planner no sync path is honest about that.

### 11. Audit record is one JSON log line on a dedicated logger

**Decision:** Every `generate_meal_plan` call — including the no-safe-plan outcome and
the invalid-input path once validation has passed the Pydantic gate — emits
`logger.info("meal_plan_audit %s", json)` on `backend.tools.audit` with: age, weight,
height, sex, diet preference, sorted allergies, doctor's note text (or null), note
extraction status, each target's value/source/band, override outcome, excluded food ids
with reasons, planned item ids, totals, and `outcome ∈ {plan, no_safe_plan}`.

**Why:** Hard rule 8 wants the snapshot to reconstruct the decision; a single JSON line is
greppable now and trivially becomes a row when the Postgres audit table lands. Invalid
input never reaches this point because Pydantic rejects it first — there is no
recommendation to audit.

### 12. Inputs are floats, outputs are rounded

**Decision:** Tool schemas take `weight_kg: float (0 < w ≤ 60)`, `height_cm: float
(0 < h ≤ 150)`, `age_months: int (0–60)`. Outputs are rounded: kcal to whole numbers,
grams and milligrams to one decimal, BMI to two.

**Why:** Day 1 chose `Numeric` for *stored* weight so the database never holds a binary
approximation. Tool inputs arrive from a request or the model, not the database, and
every output is rounded to display precision, so float arithmetic cannot surface a
representation error to a parent. The upper bounds are sanity limits, not medical ones.

## Risks / Trade-offs

- [Food-table nutrient values are hand-entered from USDA typical figures] → each entry
  carries its source; the header states values are rounded typical figures per serving;
  a test asserts every entry has a non-empty source; the table is small enough to review.
- [Greedy composition can overshoot iron: the coverage pass picks each group's most
  iron-rich food, and the calorie top-up reuses plan foods once the item cap is reached] →
  no serving may exceed the DRI upper intake level (40 mg), overshoot per shortfall is
  bounded to one serving by best-fit, and `coverage.iron` is reported so Day 5 can show
  it. Sample plans at 9–60 months land at 1.2–2.9× the iron target, 12–28 mg.
- [Greedy composition can undershoot a target] → the result reports totals next to
  targets and a `coverage` fraction per nutrient; the disclaimer and the pediatrician
  line are on every plan. Day 6 evaluation can motivate a better composer.
- [LLM extraction misreads a note (e.g. picks "800" from "not 800 kcal")] → the override is
  reported explicitly (nutrient, value, direction, and the outcome) so a parent sees what
  was applied; Day 5 UI will surface it; extraction is temperature 0 with a narrow schema.
- [Doctor's notes about foods rather than nutrients are not applied] → status
  `no_numeric_target` says so; the note text is still in the audit log.
- [Height required at 36+ months makes the planner stricter than the profile schema] →
  the validation message states the reason; `ChildProfile` gains no column this week per
  the proposal's non-goals.
- [Importing `DISCLAIMER` from `backend.rag.prompts` couples tools to the RAG package] →
  it is a string constant in a module with no network or model construction at import;
  keeping one disclaimer beats duplicating the text.

## Migration Plan

No schema, dependency, or endpoint changes. Deploy is a code push; rollback is a revert.
`nutrition-data/foods.yaml` is committed alongside the code that reads it.
