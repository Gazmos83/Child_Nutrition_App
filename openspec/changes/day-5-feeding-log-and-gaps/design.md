## Context

See proposal.md — Why. Relevant current state:

- `backend/tools/meal_plan.py` — `generate_meal_plan(request, chat_model, table)` runs
  `_general_targets` → `extract_override` → `apply_override` → diet filter → safety filter
  → `_compose(eligible, targets, age)` → `assert_plan_safe` → totals → `_audit`. `_pick`
  ranks by iron per serving; step 3 of `_compose` closes the larger of the protein/iron
  shortfalls. Outcomes are `plan | no_safe_plan`. Audit is one JSON line on
  `backend.tools.audit` (Day 4 Decision 11).
- `nutrition-data/foods.yaml` — `breast_milk` and `infant_formula_iron_fortified` are the
  two `milk_feed` entries, both per 100 ml; every solid is per `g`. `FoodItem` carries
  `serving_size`/`serving_unit` and the six nutrients.
- `backend/nutrition/` has no LangChain import (Day 4 Decision 1); `backend/tools/` is what
  the router binds. `backend/schemas/tools.py` holds every tool model with `_Strict` inputs
  and `_Frozen` outputs.
- `day-5-router-and-ui` provides `ChatRequest`, `resolve_context()` (the authority seam
  for request-supplied arguments), `ToolActivity`, the `tool` SSE event, and the side
  panel / meal-plan card in the frontend.
- No database is reachable and no authentication exists (Day 6). Python 3.14 standard
  library provides `zoneinfo` and `uuid.uuid7`.

## Goals / Non-Goals

**Goals:**
- Everything in §9b that does not require persistence, built so that persistence on Day 6
  is a row write inside `log_feeding` and a read that replaces `request.feeding_log`.
- The planner's existing behaviour is provably unchanged when the new inputs are absent.
- Gap detection is explainable in one sentence per flag ("3-day average 6.2 mg vs 11 mg
  target, source NIH DRI, 7–12 months").

**Non-Goals:**
- Any change to the safety filter's rule set, the doctor's-note extraction, or the
  composition constants.
- Nutrients other than calories, protein, iron in gap flags (calcium etc. are summed and
  shown, not flagged).

## Decisions

### 1. Placement: rules in `backend/nutrition/`, callables in `backend/tools/`

**Decision:** `backend/nutrition/feeding.py` (entry normalisation against the table,
per-entry nutrients, grouping by local day, daily totals, completeness) and
`backend/nutrition/gaps.py` (window rules and report computation) are pure Python with
no LangChain import. `backend/tools/feeding_log.py` and `backend/tools/nutrient_gaps.py`
wrap them as tools; models live in `backend/schemas/tools.py`.

**Why:** Day 4 Decision 1's invariant — `grep -r langchain backend/nutrition` is empty —
is the proof that intake arithmetic is model-free. Gap detection is exactly the kind of
"number a parent acts on" that belongs behind it.

### 2. `FeedingType` is a `StrEnum` in `backend/models/enums.py`; its PostgreSQL mirror waits

**Decision:** Add `FeedingType(StrEnum)` with `BREASTMILK, FORMULA, SOLID, WATER` beside
the existing vocabularies. The `pg_enum` mirror is created by the Day 6 migration that
creates the `feeding_log` table; no ORM model today.

**Why:** Hard rule 2 wants a closed vocabulary at the schema layer, and the enums module is
its single source of truth. Adding a table without a reachable database would produce
untestable code.

### 3. `FeedingEntry`: strict input, normalised by the table, quantity optional only for breast milk

**Decision:**

```
FeedingEntry(_Strict): id: str | None, fed_at: AwareDatetime, feeding_type: FeedingType,
                       food_id: str | None, quantity: float | None (gt=0), unit: Literal["ml","g"]
```

Pydantic-level rules: `quantity` required unless `feeding_type == breastmilk`; `solid`
requires `food_id`; `water` forbids one. Table-level normalisation in
`nutrition/feeding.py:normalise_entry(entry, table) -> NormalisedEntry`: `breastmilk` →
`breast_milk`; `formula` → `infant_formula_iron_fortified` unless another `milk_feed` id
is given; `solid` → the id must exist (`FoodNotFoundError`) and `unit` must equal the
food's `serving_unit`; `water` → no food. Nutrients = `quantity / serving_size × per-
serving` → `NutrientTotals`, zeros when unquantified or water. `log_feeding` assigns
`id = str(uuid.uuid7())` when absent.

**Why:** Two validation layers mirror Day 4 (Pydantic shape, then table facts). Splitting
them keeps the Pydantic model free of table I/O so `ChatRequest` can embed it. Optional
quantity for breast milk is the honest model of direct breastfeeding; imputing a volume
would be a number the system made up.

**Alternative considered:** a `quantity_unknown: bool` flag. Rejected — `None` already
says it, and a boolean plus a number invites contradictory states.

### 4. Days are local calendar days in a client-supplied IANA time zone

**Decision:** `ChatRequest` (and `GapDetectionRequest`, `DailyNutritionInput`,
`RemainingTargetsInput`) carry `timezone: str = "UTC"`, validated by constructing
`zoneinfo.ZoneInfo`. `group_by_day` converts each `fed_at` to that zone before taking the
date. A day is *complete* if it has ≥ 1 entry and no unquantified entry.

**Why:** "Today" is the parent's today; a 23:30 feed must not land on tomorrow because the
server is in UTC. Validation at the schema keeps a bad zone out before any tool runs.

### 5. `detect_nutrient_gaps` is async and reuses the planner's target resolution

**Decision:** Extract `resolve_targets(request_like, chat_model) -> (NutrientTargets,
NoteExtraction, OverrideOutcome)` from `generate_meal_plan` (the existing three lines:
`_general_targets` → `extract_override` → `apply_override`) into `backend/tools/targets_resolution.py`,
used unchanged by the planner and by `detect_nutrient_gaps` and `get_remaining_targets`.
Both new tools are coroutines (Day 4 Decision 10 reasoning); `get_daily_nutrition` and
`log_feeding` are sync.

**Why:** Measuring intake against the *general* target when a clinician has set a lower
one would flag a false deficit — the exact "silent blend" hard rule 3 forbids. Sharing the
resolution function means there is one definition of "the child's target".

### 6. Gap algorithm: constants, pure function, reference day excluded

**Decision:** In `backend/nutrition/gaps.py`:

```
GAP_BELOW = 0.80; GAP_ABOVE = 1.20; LOOKBACK_DAYS = 14
WINDOWS = ((7, 7, "high"), (3, 3, "medium"), (1, None, "low"))   # (min_days, window, confidence)
compute_gap_report(daily: dict[date, DayTotals], targets, as_of: date) -> NutrientGapReport
```

Complete days strictly before `as_of` and within `LOOKBACK_DAYS` are sorted descending;
`days_logged = len(complete)`; 0 → `insufficient_data`; otherwise the first `WINDOWS`
row whose `min_days ≤ days_logged` sets `window_days` (or `days_logged` for `low`) and
`confidence`. Averages over the most recent `window_days` complete days; per nutrient
`ratio = avg / target`, flag by thresholds; `low` reports carry `directional=True`.
`as_of` defaults to today in the request's time zone; the tool exposes it so tests are
deterministic and so "as of yesterday" is possible.

**Why:** Every clause in §9b's table maps to a constant or a row here; the function has no
I/O, so its tests are tables of inputs and expected reports. Excluding the reference day is
what makes a morning query not report "below" because lunch hasn't happened.

### 7. Planner extension: priority nutrient and intake subtraction, both opt-in

**Decision:** `MealPlanRequest` gains `gaps: NutrientGapReport | None = None`,
`logged_today: list[FeedingEntry] = []`, `timezone: str = "UTC"`. In `generate_meal_plan`:

1. After `resolve_targets`, if `logged_today` is non-empty, compute `already_logged`
   (normalised nutrients summed) and derive *composition targets* = targets minus intake,
   floored at 0. If remaining calories `< TARGETS_MET_SHARE (0.10) × calorie target` →
   outcome `targets_met`, no items, `message = TARGETS_MET_MESSAGE` ("Today's already
   covered — what you've logged meets the day's targets. Nothing more to plan; enjoy the
   rest of it", in `backend/chat/copy.py` per change 1 Decision 13), audit, return. Reported `targets` stay the
   full-day targets; `coverage` is computed against composition targets.
2. `priority = next(g.nutrient for g in gaps.gaps if g.flag == "below" and gaps.confidence in {"medium","high"})` else `None`;
   only `protein` or `iron` can be a priority (a calorie gap is already what step 3 fills).
   `_pick(candidates, priority)` ranks by the priority nutrient's per-serving value
   (default iron, as today); in `_compose` step 3, when both shortfalls are non-zero the
   priority nutrient wins ties. Each effect appends an `Adjustment(nutrient, action,
   confidence, detail)`. Targets and `IRON_UL_MG` are untouched.
3. With `gaps=None` and `logged_today=[]`, `priority=None` and composition targets equal
   targets — the code path is identical to today and `tests/test_tools_meal_plan.py`
   gains an equality regression over the existing fixtures.

**Why:** §9b asks for adjustment "through the existing generate_meal_plan, not a new
generation path" and for the same override hierarchy. Steering *selection* rather than
*targets* keeps every quantity traceable to a DRI value and keeps upper limits intact —
the planner never recommends more than the reference because the log says intake was low.

**Alternative considered:** raising the flagged nutrient's target by the observed
shortfall. Rejected: it turns a measurement into a prescription, and would collide with
the doctor's-note override semantics.

### 8. Audit: extend the existing record; one new record for gap detection

**Decision:** `_audit` adds `gaps` (`status, confidence, days_logged, window_days, flags:
{nutrient: flag}`), `logged_today` (`[{id, fed_at, feeding_type, food_id}]` plus
`already_logged` totals), `adjustments`, and `outcome ∈ {plan, no_safe_plan,
targets_met}`. `detect_nutrient_gaps` emits `nutrient_gaps_audit {input, days_logged,
partial_days, window_days, confidence, gaps[], override}` on the same `backend.tools.audit`
logger, including for `insufficient_data`.

**Why:** Hard rule 8 plus §9b's "which feeding-log entries and detected gaps informed the
adjustment", on the logger Day 6 already plans to persist.

### 9. Router integration: log-backed fields are context, resolved like profile fields

**Decision:** `ChatRequest` gains `feeding_log: list[FeedingEntry] = []` (≤ 200) and
`timezone`. In `resolve_context`, `LOG_FIELDS = {entries, logged_today, timezone}`:
`entries` ← all of `request.feeding_log`; `logged_today` ← entries whose local date is
today; `timezone` ← request. These overwrite anything the model proposed and appear in
`used_context`. `generate_meal_plan`'s new fields are filled the same way; its `gaps`
argument is filled only if the model also called `detect_nutrient_gaps` in the same turn
— otherwise the service runs gap detection itself before the planner when `feeding_log` is
non-empty, so "plan the rest of today" gets the adjustment without the model having to
remember to ask.

**Why:** The model must never transcribe a log (it would drop or invent entries). Running
detection implicitly before a plan when a log exists is the §9b behaviour ("output feeds
generate_meal_plan"), made deterministic rather than dependent on the model's tool
choreography.

### 10. Endpoints: `POST /api/feedings` and `GET /api/foods`, stateless

**Decision:** `backend/api/feedings.py` runs `log_feeding()` on a single `FeedingEntry`
and returns `LoggedFeeding`; `FoodNotFoundError` → 422 naming the id. `backend/api/foods.py`
returns `FoodSummary[]` from `get_food_table()`. Both on `api_router`, both take no
identity; the feedings handler is the Day 6 persistence point.

**Why:** The manual form should not route through the LLM to validate a formula bottle;
one shared function serves the tool and the endpoint so Day 6 adds the write once.

### 11. Frontend: local log store, picker from `/api/foods`, cards from tool results

**Decision:** `src/lib/feeding-log-store.ts` is pure (`add`, `remove`, `pruneOlderThan(14
days)`, `todayEntries(tz)`, `serialize/deserialize`) and mirrored to `localStorage`.
`log-feed-form.tsx` posts to `/api/feedings` and appends the returned `LoggedFeeding`; the
reducer also appends on a `tool` event named `log_feeding` with `status: "ok"`. `use-foods`
is a `useQuery` on `/api/foods`. `gap-report-card.tsx` renders from the
`detect_nutrient_gaps` result; `meal-plan-card.tsx` gains `adjustments`, `already_logged`,
and the `targets_met` state. "Today so far" sums the server-returned nutrients of today's
entries; targets are shown only when a tool result provides them (no client arithmetic
against DRI tables).

**Why:** Same principle as the meal-plan card: provenance and numbers come from structured
results, never from the model's prose or from client-side reimplementation of the tables.

### 12. Copy for the feeding log and gap card (extends change 1 Decision 13)

**Decision:** The same tone guide and the same two copy modules. Everyday states are warm
and a little playful; anything that could read as a verdict on the parent's feeding —
a "below" flag, an excluded day — is warm and direct, and says what it does *not* mean.
Added strings:

| Key | Copy |
|---|---|
| `LOG_EMPTY` | Nothing logged yet. Add a feed whenever you like — the more days we see, the more we can tell you |
| `TODAY_EMPTY` | A blank slate — today's just getting started |
| `LOG_STORED_HERE` | Your log lives in this browser for now — fourteen days, then it tidies itself |
| `FEED_LOGGED` (after a successful add) | Logged. One more piece of the picture |
| `GAPS_INSUFFICIENT` | We need a few full days of feeds before we can spot patterns. Keep logging and we'll say when we can see enough |
| `GAPS_LOW` | Early days — here's a first look. Take it lightly until there's more to go on |
| `gapsWindow(days, window)` | Based on {days} full days, looking at the last {window} |
| `partialDaysNote(n)` | {n} day(s) had a breastfeed without a measure, so we left them out — that's normal, not a problem |
| `FLAG_BELOW` / `FLAG_ADEQUATE` / `FLAG_ABOVE` | A little short of target · On track · Above target |
| `FLAG_BELOW_NOTE` | Averages, not a verdict — one lighter day is fine. This is a nudge toward foods rich in it |
| `TARGETS_MET_MESSAGE` (backend) | Today's already covered — what you've logged meets the day's targets. Nothing more to plan; enjoy the rest of it |
| `adjustedFor(nutrient, days)` | Adjusted for {nutrient} — intake has been a little short over the last {days} days, so we leaned toward {nutrient}-rich foods |
| `alreadyLogged(kcal, protein, iron)` | Already logged today: {kcal} kcal · {protein} g protein · {iron} mg iron |
| `REMAINING_COVERED` (per nutrient at zero remaining) | Covered for today |
| `FORM_QUANTITY_BREASTMILK_HINT` | No measure? Leave it blank — we'll count the feed and skip the maths for that day |

**Why:** The gap card is the one place this product tells a parent their child got less
than a target. The copy makes the frame explicit — averages, a nudge, not a judgement — and
the excluded-day note prevents "we left them out" from reading as "you did it wrong".

## Risks / Trade-offs

- [Day 5 is over-full: router + UI already fill it] → this change is separate and ordered
  second; the cut line (proposal) is Decision 7 step 1 (`logged_today`/`targets_met`),
  then `get_daily_nutrition`/`get_remaining_targets`, then card polish. Each remaining
  piece still ships coherent behaviour.
- [Exclusively breastfed infants never get gap flags] → intended (intake unknown); the
  card explains "not enough complete days" and the report counts `partial_days` so the
  parent sees why.
- [The reference-day exclusion means a parent logging their first day sees nothing until
  tomorrow] → the card says so explicitly; "today so far" totals and remaining targets are
  available immediately.
- [Composition-priority change alters plans in ways that surprise] → adjustments are
  reported on the card and in audit; a `low` flag changes nothing; only `protein`/`iron`
  can be priorities.
- [Client-held log is lost if the browser storage is cleared] → accepted for Day 5;
  persistence is Day 6. The panel states that the log is stored in this browser.
- [`timezone` from the client is wrong] → worst case a feed lands on an adjacent day; the
  value is validated as an IANA zone and shown on the panel.

## Migration Plan

1. Enum + schemas + `nutrition/feeding.py` + `nutrition/gaps.py` with tests (pure).
2. `resolve_targets` extraction (planner tests unchanged) → tools → planner extension with
   the equality regression → langchain wrappers → endpoints.
3. Router/chat integration → frontend tab and cards → end-to-end.

**Rollback:** remove the four tools from `build_tools`, the two endpoints from
`api_router`, and the optional planner fields; `generate_meal_plan` without them is the
Day 4 code path. The `resolve_targets` extraction is behaviour-neutral and can stay.

**Day 6 hand-off:** create `feeding_log` table + `feeding_type` enum migration; `log_feeding`
writes a row for the authenticated user's child; `resolve_context` reads the log by
`child_profile_id` instead of `request.feeding_log`; `/api/feedings` gains auth and
persistence; frontend replaces the local store with server reads. No change to
`nutrition/` or `gaps.py`.
