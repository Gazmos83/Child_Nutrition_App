## Context

See proposal.md — Why. Relevant current state:

- `backend/schemas/tools.py`: `FoodLookupInput(_Strict)` has one field, `food_id`;
  `MealItem(_Strict)` has `food_id` and `servings` (gt 0, ≤ 20, "multiples of the food's
  table serving"); `FoodRecord(FoodItem)` adds `resolved_source`. `FeedingUnit =
  Literal["ml", "g"]` and `MAX_FEED_QUANTITY = 2000.0` are defined further down, in the
  feeding-log section.
- `backend/nutrition/foods.py:LoadedFoodTable.resolve`: exact id → normalized id/name →
  unique token subset (all non-stopword query tokens must appear in one food's pool; several
  → refusal with candidates) → difflib close matches. `_STOPWORDS` is a short list of
  articles and conjunctions; preparation words are deliberately not in it. The committed
  pools contain `iron` and `calcium` (fortified foods, calcium-set tofu), so nutrient names
  cannot be treated as noise. `FoodNotFoundError.food_id` is the string as given; the chat
  layer classifies failures by the "Unknown food" message prefix.
- `backend/nutrition/feeding.py`: `entry_nutrients(food, quantity)` scales per-serving values
  by `quantity / serving_size` (two decimals); `normalise_entry` raises `FeedingEntryError`
  "X is measured in g, not ml" on a unit mismatch; `backend/api/children.py` maps
  `FeedingEntryError` to 422.
- `backend/chat/service.py:_invoke` maps `FoodNotFoundError` to `copy.unknown_food(...)`;
  any other exception becomes the generic `TOOL_FAILED`; `_error_kind` classifies by
  message prefix. `backend/chat/prompts.py` pins phrases asserted by
  `tests/test_chat_prompts.py` ("Growth questions", "Never recompute", …).
- `backend/tools/langchain_tools.py` descriptions are what the router routes on.
- Frontend: a `lookup_food` result renders as the tool chip (`copy.toolSummary`) plus raw
  JSON behind "Show details"; no card.
- `evals/cases.yaml` has 54 cases (`tests/test_eval_cases.py` allows 40–60); the harness
  checks that expected tools ended `ok`, not their arguments.

## Goals / Non-Goals

**Goals:**
- The parent's amount reaches the tool as a number and comes back as numbers computed in
  code; the model only relays.
- A food name surrounded by amount and question words resolves exactly as the bare name
  would; the lookalike refusal and the preparation-word discrimination are untouched.
- No existing resolver test changes; the new behaviour is covered by added cases and a
  disjointness guard.

**Non-Goals:**
- Anything under proposal.md — Non-goals.

## Decisions

### 1. Quantity and unit are optional fields on the lookup input; a missing unit means the food's own

**Decision:** `FoodLookupInput.quantity: float | None` (gt 0, ≤ `MAX_FEED_QUANTITY`) and
`unit: FeedingUnit | None`; a validator rejects a unit without a quantity. When `unit` is
omitted the food's `serving_unit` is used and echoed back as `requested_unit`. `FoodRecord`
gains `requested_quantity`, `requested_unit`, `nutrients_for_quantity: NutrientTotals | None`;
the per-serving record stays as it is.

**Why:** The pipeline is single-shot with no retry, each food has exactly one unit, and the
parent's number should be used as given rather than refused for a missing word. Echoing the
unit keeps nothing silent. Keeping the per-serving values lets the answer name the serving
as context.

**Alternative:** require the unit — rejected: "20 grams of sweet potato" and "20 of sweet
potato" would then differ in outcome for no safety gain.

### 2. Meal items accept a quantity with unit as an alternative to servings

**Decision:** `MealItem.servings` becomes optional; `quantity` and `unit` are added; exactly
one of `servings` or `quantity` must be given. Summation uses the same `entry_nutrients`
helper for quantity items. A unit mismatch fails the whole call (no silent skipping);
`missing` stays reserved for unknown foods.

**Why:** The existing eval case "150 ml of formula plus 30 g of cereal" has the identical
root cause — the model must divide by serving sizes (100 ml, 15 g) it has never seen, and
a wrong divisor cannot fail. Fifteen lines reuse the same helper; the result shape is
unchanged.

### 3. One unit check, shared by the feeding log and the tools

**Decision:** `backend/nutrition/feeding.py` gains `UnitMismatchError(FeedingEntryError)`
carrying `food_name`, `expected_unit`, `given_unit`, and `check_unit(food, unit)`;
`normalise_entry` calls it with the same message text. `nutrient_tools._for_quantity(food,
quantity, unit)` resolves the default unit, calls `check_unit`, then `entry_nutrients`.

**Why:** The feeding log's 422 path (`except FeedingEntryError`) keeps working because the
new class is a subclass; the chat gets a typed exception to map to parent-facing copy
instead of the generic failure.

### 4. The resolver ignores noise on the query side only

**Decision:** After stopword removal, `resolve` drops every token whose first character is a
digit or that is in `_QUERY_NOISE` — units (g, gram(s), ml, millilitre(s)/milliliter(s), oz,
ounce(s), cup(s), tbsp, tablespoon(s), tsp, teaspoon(s)), measure words (piece(s),
serving(s), portion(s), half, quarter, some, about, roughly, approximately, around, per,
for), question words (what, how, many, much, is, are, does, do, have, has, there), and
framing words (nutritional, nutrition, nutrient(s), value(s), calories, kcal, macros). If
nothing is left, the original tokens are kept so "20 grams" and "iron" behave as today.
When stripping removed anything, the normalized-equality step is retried on the joined core
("a serving of avocado" → "avocado") before the unique-subset step; difflib uses the core;
`FoodNotFoundError.food_id` keeps the original string. The index (`_tokenize`) is untouched.
A test asserts `_QUERY_NOISE` is disjoint from every committed pool.

**Why:** Preparation words must keep discriminating (`carrot_cooked_mashed` vs
`raw_carrot_sticks`) and nutrient names occur in pools, so a bounded, reviewable list is the
only safe noise set. Query-side stripping leaves the "refuse lookalikes" rule exactly as
specified.

**Alternative rejected:** dropping any token that occurs in no pool. It would make "banana
mashd" resolve to `banana_mashed` and "chicken brest" to `chicken_breast_shredded`, turning
the spec's "refused with closest matches" path into silent typo acceptance and reversing
an existing test. The schema and prompt changes already put only the food in `food_id`; the
noise list is defence in depth.

### 5. Chat maps the unit mismatch to one direct sentence

**Decision:** `_invoke` gains `except UnitMismatchError` → `ToolActivity(status="error",
error=copy.wrong_unit(food_name, expected, given), detail=str(exc))`;
`copy.wrong_unit` reads "{food} is measured in {expected}, not {given} — give the amount in
{expected} and we'll work it out". `_error_kind` falls through to `"validation"`.

**Why:** The parent asked in the wrong unit; the fix is one word, and the message says
which. Same voice as `unknown_food`.

**Known edge:** a model-supplied `quantity: 0` trips the existing `_validation_message`
"input == 0" rule and yields the missing-field hint naming "quantity"; restricting that rule
to profile fields is [Stretch].

### 6. Prompts name the argument shape; pinned phrases survive

**Decision:** Router: one bullet after the nutrient-tools bullet — a question about one
food's nutrients goes to `lookup_food`; `food_id` is the food only ("sweet potato", never
"20 grams of sweet potatoes"); an amount goes in `quantity` with `unit` g or ml; several
foods with amounts go to `calculate_meal_nutrition`, one item per food. Answer: one bullet —
when a lookup carries `nutrients_for_quantity`, lead with those figures for the requested
quantity and unit and mention the serving as context; otherwise give per-serving figures and
name the serving; never scale between them. Tool descriptions restated to match. Every
phrase `tests/test_chat_prompts.py` asserts is kept verbatim.

### 7. Frontend: the chip says the amount; no card

**Decision:** `toolSummary("lookup_food", args, result)` reads `args.quantity` and
`args.unit ?? result.requested_unit` and renders "Looked up 20 g of Sweet potato, cooked
and mashed" when both are present, else the existing line. Added to `RENDERED` in the copy
test.

**Why:** The answer text carries the numbers; the chip's raw JSON already shows
`nutrients_for_quantity`. A two-column card is [Stretch].

## Risks / Trade-offs

- [A future food whose id or name contains a noise word] → the disjointness test fails at
  commit time and the word is removed from the list or the food renamed.
- [Router still passes the amount inside `food_id`] → the resolver's noise rule resolves it
  anyway and the answer gives per-serving figures; the eval case checks the tool ended ok.
- [Unit mismatch in a meal fails the whole call] → deliberate: a silently skipped item would
  understate a total; the message names the food and unit.
- [Prompt growth] → two bullets and two description edits, all pinned by tests.

## Migration Plan

Purely additive; no data, no schema, no config. Rollback is reverting the commit.
