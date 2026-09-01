# Design — food-name-resolution

## Context

See proposal.md — Why. Current state: `LoadedFoodTable.get()`
(`backend/nutrition/foods.py`) is an exact dict lookup whose docstring promises "never a
default or a lookalike"; the chat pipeline (`backend/chat/service.py`) is single-shot —
one routing call, one tool pass, one answer, no retry — and tool calls are not replayed
into history, so the model re-invents `food_id` every turn. The valid ids live only in
`nutrition-data/foods.yaml` (57 entries) and `GET /api/foods` (frontend picker).
Constraints: deterministic code over LLM behavior (architecture principle), minimal
diff, `_error_kind` in `backend/chat/service.py` string-matches the `"Unknown food"`
message prefix, `FoodItem` is `extra="forbid"`.

## Goals / Non-Goals

**Goals:**
- A parent-worded food name resolves to its table entry in plain Python, first try.
- Anything ambiguous or unknown fails fast with actionable candidates in the one
  answer the single-shot pipeline gets to produce.
- Zero behavior change for exact-id callers (frontend picker, feeding log, planner).

**Non-Goals:**
- See proposal.md — Non-goals (no aliases field, no retry loop, no prompt id lists, no
  fuzzy auto-acceptance, feeding-log persistence untouched).

## Decisions

**D1 — Resolve in the table, not in the tool layer.** `LoadedFoodTable.resolve(query)`
sits next to `get()` so any tool can opt in, the token index is built once in
`__init__` (table is immutable; `lru_cache` on `get_food_table` unchanged), and the
"never a lookalike" contract stays owned by the same class that states it.
*Alternative rejected:* a resolver module in `backend/tools/` — would duplicate table
internals and leave `calculate_meal_nutrition` a second integration point.

**D2 — Precedence: exact id → normalized equality → unique token-subset → refuse.**
Normalization: lowercase, collapse non-alphanumeric runs to single spaces, strip.
Tokenization: split, drop a small stopword set (`a and as from in its made of or the to
until with`), keep preparation words (`cooked`, `mashed`, `raw`, `whole` distinguish
`carrot_cooked_mashed` from `raw_carrot_sticks`). Plurals match via symmetric variant
sets — each token compares on {tok, tok−trailing `s`, tok−trailing `es`} computed on
both the query and index sides ("bananas"→"banana", "potatoes"→"potato"). Token-subset
succeeds only when the query's tokens are contained in exactly one food's token set
(id tokens ∪ name tokens); 2+ containers refuse with those candidates (cap 5).
*Alternative rejected:* scoring/similarity thresholds — tunable magic numbers where a
set-containment rule is exact, explainable, and testable.

**D3 — Suggestions ride the existing exception.** `FoodNotFoundError` gains a
`suggestions: tuple[str, ...]` (formatted `"id (Name)"`), sourced from the ambiguity
set or `difflib.get_close_matches` over normalized ids+names on no-match. The message
keeps the exact `Unknown food id {...!r}` prefix — `_error_kind`'s
`startswith("Unknown food")` classification must not break — and appends
`. Closest matches: …` when suggestions exist. `copy.unknown_food` renders them as
"did you mean …?" for the parent. *Alternative rejected:* a new exception type —
every catch site would need touching for no added meaning.

**D4 — Cover `calculate_meal_nutrition` too; keep the failure shape.** Same swap
(`get`→`resolve` per item); an unresolvable string still lands in `missing` exactly as
typed, so the result schema and frontend rendering are untouched.

**D5 — Teach the model via descriptions only.** One clause in the `lookup_food` /
`calculate_meal_nutrition` tool descriptions and the `food_id` field descriptions:
plain names accepted, unknown names fail with closest matches. Field keeps the name
`food_id` (renaming ripples through evals, tests, logging, frontend). Router prompt
untouched.

## Risks / Trade-offs

- [Ambiguous one-worders ("apple", "milk", "carrot", "cheese") now fail with candidate
  lists instead of resolving] → intended: correctness over convenience; the parent gets
  named options in the same answer. Load-bearing tests pin this.
- [Naive plural stripping mismatches some singular/plural pairs (e.g. "grape" vs
  "grapes" both reduce oddly)] → variant sets are computed symmetrically on both sides,
  and difflib suggestions catch the stragglers; tests against the real table are the
  contract.
- [Spelling variants ("yogurt" vs the table's "yoghurt") won't auto-resolve] → falls
  through to difflib suggestions; if it bites in practice, that triggers the deferred
  aliases field, not more cleverness here.
- [Message-prefix coupling to `_error_kind`] → called out in tasks; a test asserts the
  `unknown_food` classification survives.
- [Existing tests assume near-misses raise (`food_id="lentil"` against fixture id
  `lentils`)] → those tests are updated to assert the new, correct resolution; exact
  `get()` strictness tests stay untouched.

## Migration Plan

Pure code change, no data or API migration. Deploy with the normal backend deploy;
rollback is a revert. `GET /api/foods`, the frontend picker, and persisted data are
unaffected.
