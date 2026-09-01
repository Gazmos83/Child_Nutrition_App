# Food-name resolution for lookup tools

## Why

[MVP] The `lookup_food` chat tool fails unpredictably in real conversations: the model
must supply an exact opaque `food_id`, but the valid id vocabulary is never exposed to
it, so it guesses a slug from the food's plain-English name each turn ("bananas" never
resolves; "sweet potatoes" resolved once, then failed as `sweet_potato_cooked_mashed` —
the slugified display name of `sweet_potato_mashed`). The chat pipeline is single-shot
with no retry, so one bad guess means a failed answer. This is a reliability bug fix to
the Day 4 deterministic tools / Day 5 routing surface, done during post-MVP polish.

## What Changes

- The food table gains a deterministic, code-only resolution step: a lookup string is
  resolved by exact id, then normalized-name equality, then unique token-subset match
  (with plural handling). Ambiguous or unrecognized strings are refused — never a
  lookalike — and the refusal carries closest-match suggestions.
- `lookup_food` and `calculate_meal_nutrition` accept a food's common name as typed by
  the parent, not only the exact id. Exact ids keep working unchanged (frontend picker,
  feeding log are untouched).
- The parent-facing unknown-food message gains "did you mean …?" suggestions and drops
  the reference to a list the chat surface doesn't have.
- Tool and field descriptions tell the model a plain name is acceptable. No router
  prompt change, no retry loop, no id enumeration in prompts.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `food-composition-data`: the "Lookup is by stable identifier" requirement is extended —
  the table also resolves a plain-language food name deterministically, refuses ambiguous
  or unknown names instead of substituting a lookalike, and reports closest matches on
  refusal.
- `deterministic-nutrient-tools`: `lookup_food` and `calculate_meal_nutrition` accept a
  food id or a common food name; resolution is deterministic Python with no
  language-model involvement.

## Impact

- `backend/nutrition/foods.py` — `LoadedFoodTable.resolve()`, token index,
  `FoodNotFoundError.suggestions`.
- `backend/tools/nutrient_tools.py` — both food tools switch from `get` to `resolve`.
- `backend/schemas/tools.py`, `backend/tools/langchain_tools.py` — description text only.
- `backend/chat/copy.py`, `backend/chat/service.py` — suggestions in the unknown-food
  message.
- No API, schema-shape, database, or frontend changes; `GET /api/foods` and the
  feeding-log picker are unaffected.

## Non-goals

- No `aliases` field in `foods.yaml` (deferred until real synonym gaps appear, e.g.
  regional spellings).
- No retry loop or second routing pass — the single-shot chat architecture stays.
- No id list embedded in prompts or tool descriptions.
- No fuzzy auto-acceptance: close matches are suggested, never silently chosen.
- Feeding-log persistence (`log_feeding`) keeps requiring exact ids — resolving free
  text before persisting data is a separate decision.
