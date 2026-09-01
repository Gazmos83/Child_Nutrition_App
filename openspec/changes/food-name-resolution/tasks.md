# Tasks — food-name-resolution

## 1. Resolver in the food table

- [x] 1.1 In `backend/nutrition/foods.py`, extend `FoodNotFoundError` with
  `suggestions: tuple[str, ...] = ()` (formatted `"id (Name)"`), keeping the exact
  message prefix `Unknown food id {food_id!r}` and appending `. Closest matches: …`
  when suggestions exist; verify existing `uv run pytest tests/test_nutrition_foods.py -q`
  still passes.
- [x] 1.2 Add `_normalize`/`_tokenize` helpers (lowercase, non-alphanumeric runs →
  spaces; stopwords `a and as from in its made of or the to until with`; symmetric
  plural variant sets {tok, tok−`s`, tok−`es`}), build the token index in
  `LoadedFoodTable.__init__`, and implement `resolve(query)` with precedence exact id →
  normalized id/name equality → unique token-subset → refuse (ambiguity candidates
  capped at 5, else `difflib.get_close_matches` suggestions). `get()` unchanged. Verify
  with the new resolver tests in 3.1.

## 2. Tools, descriptions, and copy

- [x] 2.1 In `backend/tools/nutrient_tools.py`, switch `lookup_food` and
  `calculate_meal_nutrition` from `table.get(...)` to `table.resolve(...)`; an
  unresolvable meal item still appends the original string to `missing`. Verify
  `uv run pytest tests/test_tools_nutrient.py -q`.
- [x] 2.2 Update description text only: `FoodLookupInput.food_id` and `MealItem.food_id`
  in `backend/schemas/tools.py`, and the `lookup_food`/`calculate_meal_nutrition` tool
  descriptions in `backend/tools/langchain_tools.py` — accepts the table id or the
  food's plain name; unknown names fail with closest matches. Verify
  `uv run pytest tests/test_tools_langchain.py -q`.
- [x] 2.3 In `backend/chat/copy.py`, extend `unknown_food(food_id, suggestions=())` to
  render "— did you mean {display names}?" when suggestions exist and drop the
  "try picking one from the list" clause otherwise (keep the direct error voice); in
  `backend/chat/service.py`, pass `exc.suggestions` through. Verify
  `uv run pytest tests/test_chat_service.py -q` including an assertion that
  `_error_kind` still classifies the failure as `unknown_food`.

## 3. Tests

- [x] 3.1 Add resolver tests against the real committed table (precedent:
  `test_committed_table_by_default`): "bananas" → `banana_mashed`; "sweet potatoes",
  "sweet potato cooked mashed", and the literal `sweet_potato_cooked_mashed` →
  `sweet_potato_mashed`; exact-id passthrough (`avocado`); danger entries resolve with
  flags intact (`grapes` → `whole_grapes` choking hazard, `honey` → contains honey);
  ambiguity refuses with all candidates in `.suggestions` for "carrot", "milk",
  "apple", "cheese"; unknown string raises preserving `.food_id` with difflib
  suggestions; `calculate_meal_nutrition` counts `"bananas"` and reports garbage as
  typed in `missing`; `copy.unknown_food("x", ["Banana, mashed"])` renders the
  suggestion. Verify `uv run pytest tests/test_tools_nutrient.py tests/test_nutrition_foods.py -q`.
- [x] 3.2 Update tests broken by resolution being more capable: split
  `test_unknown_id_raises` (fixture `"lentil"` now resolves to `lentils`; use a truly
  unknown string for the raise case) and align `tests/test_chat_service.py` expected
  unknown-food error strings with the new copy signature. Leave
  `tests/test_nutrition_foods.py` `get("bananas")`-raises untouched (exact `get` stays
  strict). Verify `uv run pytest -q` (full suite) passes.

## 4. End-to-end verification

- [x] 4.1 Manual chat smoke (backend + frontend running, signed in — chat requests are
  auth-scoped as today; the food table itself is global, not user data): "What
  nutrients are in bananas?" → `lookup_food` activity ok with `banana_mashed`; "how
  about sweet potatoes?" → `sweet_potato_mashed`; "what about carrots?" → error
  activity whose copy names the cooked-mashed and raw-sticks options; confirm the
  frontend feeding-log picker still logs foods (exact-id path) and the `tool-food-lookup`
  eval case is unaffected.
