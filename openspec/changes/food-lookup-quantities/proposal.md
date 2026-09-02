## Why

A parent asked the chat "what are the nutritional values for 20 grams of sweet potatoes"
and was told "We don't know a food called “20 grams of sweet potatoes” yet". The table knows
sweet potato; three things between the parent and the answer do not. The `lookup_food` tool
has no quantity field, so the model stuffs the whole phrase into `food_id` or drops the 20 g.
The name resolver requires *every* word of the query to belong to a food, so "20", "grams",
"nutritional" turn a good name into a refusal with no suggestions. And the answer prompt
forbids the model from scaling the table's 60 g serving down to 20 g, so even a successful
lookup could only report a serving the parent did not ask about.

**Scope: [MVP] polish of an existing MVP tool (post-Day-7 follow-on, Day 11 in the project's
numbering).** No new tool, no model arithmetic, no new dependency.

## What Changes

- **A quantity on food lookups.** `lookup_food` takes an optional `quantity` and `unit`
  (`g` or `ml`); when given, the result also carries the nutrients for exactly that amount,
  computed in code as `quantity ÷ serving size × per-serving` — the same arithmetic the
  feeding log already uses. A unit that contradicts the table (ml of a solid) is refused
  naming the food's unit. `calculate_meal_nutrition` items may give a quantity with unit
  instead of `servings`, so "150 ml of formula plus 30 g of cereal" no longer needs the
  model to divide by serving sizes it has never seen.
- **A noise-tolerant resolver.** Amount words (numbers, units, measure words) and question
  words around a food name are ignored for matching and never used to choose between foods.
  Preparation words (cooked, mashed, raw, whole) and nutrient names keep discriminating,
  and the "refuse lookalikes" rule is untouched: "carrot", "milk", "apple", "cheese" are
  still refused with their candidates named.
- **Prompts that name the shape.** The router example "nutritional values for 20 g of
  sweet potato" → `lookup_food` with the food only in `food_id` and the amount in
  `quantity`/`unit`; the answer prompt leads with the per-quantity figures when present and
  the per-serving figures otherwise, still never scaling itself; tool descriptions say the
  same.
- **A tool chip that shows the amount** ("Looked up 20 g of Sweet potato, cooked and
  mashed").

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `deterministic-nutrient-tools`: `lookup_food` accepts a quantity and unit and returns the
  nutrients for that amount; `calculate_meal_nutrition` items accept a quantity with unit as
  an alternative to servings; a contradicting unit is refused naming the table's unit.
- `food-composition-data`: plain-language resolution ignores amount and question words
  around the food name; a string made only of such words is refused with the string
  preserved.
- `intent-routing`: a question about one food with an amount routes to the food lookup with
  the food name and the amount in separate arguments.

## Impact

- **Backend**: `backend/schemas/tools.py` (`FoodLookupInput`, `MealItem`, `FoodRecord`),
  `backend/nutrition/feeding.py` (`UnitMismatchError`, `check_unit`),
  `backend/nutrition/foods.py` (query-side noise rule in `resolve`),
  `backend/tools/nutrient_tools.py`, `backend/chat/service.py` + `backend/chat/copy.py`
  (one new parent-facing string), `backend/chat/prompts.py`, `backend/tools/langchain_tools.py`.
- **Frontend**: `frontend/src/lib/copy.ts` (`toolSummary` for `lookup_food`) and its test.
- **Evals**: one new case in `evals/cases.yaml` (55 of the allowed 40–60).
- **API contract**: additive — two optional fields on a tool input, one optional pair on meal
  items, three optional fields on the lookup result. Chat SSE unchanged.
- **Dependencies, data, security**: none; no user-scoped operation.

## Non-goals

- Unit conversion (ounces, cups, tablespoons) — the table is in g and ml; a parent's "oz" is
  refused, not guessed. [Stretch]
- A synonym table ("yogurt"/"yoghurt", "courgette"/"zucchini") — separate concern. [Stretch]
- A second resolution attempt within one chat turn — the pipeline stays single-shot.
- A dedicated lookup result card — the answer carries the figures; the chip's details show
  the JSON. [Stretch]
- Silent typo acceptance — dropping words that match no food would turn "banana mashd" into
  a guess; the spec's "refused with closest matches" path stands.
