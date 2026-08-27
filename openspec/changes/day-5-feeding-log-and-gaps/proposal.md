## Why

Every number the assistant can produce today is a *target* — what a child of this age and
weight should get. Nothing captures what the child actually got, so the assistant cannot
tell a parent "she's been short on iron for three days" or plan the rest of a day around
what was already eaten. Reference §9b adds that missing half: a feeding log of actual
intake, deterministic detection of nutrient gaps as the log grows, and daily plan
adjustment through the existing meal planner. The reference files this under Day 4, which
is complete and archived; it is scheduled here, after the router and UI it depends on.

**Scope: [MVP]. Day 5 of 7, second change.** Builds on `day-5-router-and-ui` (the chat
endpoint, router, and UI) and must be applied after it.

## What Changes

- **Feeding entries as a controlled, validated record** — an entry is a timestamp, a
  feeding type from a closed vocabulary (`breastmilk`, `formula`, `solid`, `water` —
  hard rule 2), an optional food from the curated food table, a quantity, and a unit.
  Breast milk may be logged without a quantity (direct breastfeeding is not measurable);
  every other type requires one. Nutrient content of an entry is computed from the food
  table by arithmetic, never by the model.
- **Where the log lives today** — §9b specifies a PostgreSQL table bound to the
  authenticated user. Day 5 has neither a reachable database nor authentication (both are
  Day 6, with Day 1 §7). The log is therefore **held in the browser and sent with each
  request**, exactly as child context is in the first Day 5 change, bounded to fourteen
  days and two hundred entries. The deterministic core built here is persistence-agnostic;
  on Day 6 the same `log_feeding` handler writes the row and the request field is replaced
  by an auth-scoped read. Nothing user-scoped is stored server-side today, so hard rule 9
  holds by construction.
- **Four new deterministic tools**, callable by the router and validated with Pydantic
  (hard rule 7): `log_feeding` (validate, normalise, compute nutrients — no write today),
  `get_daily_nutrition` (totals for a day), `get_remaining_targets` (targets minus intake
  for a day, doctor's note honoured), and `detect_nutrient_gaps`.
- **Nutrient-gap detection by widening rolling windows, not learning** — with no complete
  days logged there is no detection; with one or two days, low-confidence directional
  flags; from three days, a three-day average per nutrient against the child's target;
  from seven, a seven-day average with high confidence. Targets are the ones the meal
  planner uses, including a doctor's-note override, so a prescribed calorie limit is not
  reported as a deficit. Days containing an unquantified feed are excluded from windows.
- **Daily plan adjustment through `generate_meal_plan`, not a new path** — the planner
  accepts an optional gap report and today's logged entries. A gap of at least medium
  confidence changes which foods the composer prefers; it never raises a target above the
  reference values. Today's intake is subtracted so the plan covers the rest of the day,
  with a new `targets_met` outcome when little remains. With neither input the planner's
  output is identical to today's, so logging remains optional. The infant-safety filter
  and the doctor's-note override run unchanged (hard rules 3–4).
- **Audit extended (hard rule 8, §9b)** — every plan's audit record additionally names the
  gap report, the logged entries, and the adjustments that informed it; gap detection emits
  its own audit record.
- **Two small stateless endpoints for the manual form** — `POST /api/feedings` runs the
  same validation and nutrient computation as the tool (Day 6 makes it persist); `GET
  /api/foods` lists the food table for the picker. Neither reads user data.
- **UI** — a Feeding-log tab in the side panel (log-a-feed form with food picker, entries
  grouped by day with nutrients, "today so far" totals), a gap-report card in chat, and
  meal-plan card additions ("adjusted for …", "already logged today …", `targets_met`).

## Capabilities

### New Capabilities

- `feeding-log`: recording what a child was actually fed as validated, controlled-
  vocabulary entries with table-derived nutrient content; daily totals and remaining
  targets; the client-held log contract for Day 5 and its Day 6 persistence seam.
- `nutrient-gap-detection`: deterministic rolling-window comparison of logged intake to
  the child's (note-overridden) targets, with confidence that grows with days logged and
  no learning component.

### Modified Capabilities

- `meal-plan-generation`: the plan MAY additionally take a gap report and today's logged
  entries; behaviour with neither is unchanged; gaps steer composition without raising
  targets; today's intake is subtracted; new `targets_met` outcome; audit record extended
  with gaps, logged entries, and adjustments.
- `deterministic-nutrient-tools`: four new tools join the set (`log_feeding`,
  `get_daily_nutrition`, `get_remaining_targets`, `detect_nutrient_gaps`), all subject to
  the existing no-model-arithmetic and validate-before-compute requirements.
- `chat-api`: the request additionally carries the client-held feeding log and the
  client's time zone; log-backed tool arguments are filled from it, never from the model.
- `chat-ui`: the side panel gains the Feeding-log tab; the chat renders gap-report cards
  and the meal-plan card's adjustment lines.

## Impact

- **New code**: `backend/nutrition/feeding.py`, `backend/nutrition/gaps.py` (pure, no
  LangChain import — the `grep -r langchain backend/nutrition` invariant holds),
  `backend/tools/feeding_log.py`, `backend/tools/nutrient_gaps.py`,
  `backend/api/feedings.py`, `backend/api/foods.py`; frontend feeding-log tab, gap card.
- **Touched code**: `backend/models/enums.py` (+`FeedingType`; its PostgreSQL enum mirror
  ships with the Day 6 migration), `backend/schemas/tools.py` (entry/report/result
  models; two optional planner fields; `targets_met` outcome), `backend/tools/meal_plan.py`
  (targets resolution extracted for reuse; composition priority; intake subtraction;
  extended audit), `backend/tools/langchain_tools.py` (+4 tools),
  `backend/schemas/chat.py` and `backend/chat/router.py` (log context),
  `backend/api/router.py`, `tests/test_tools_langchain.py` (expected names), `README.md`,
  `CLAUDE.md` (MVP scope line names the feeding log and gap detection).
- **API surface**: `POST /api/feedings`, `GET /api/foods`; `POST /api/chat` request gains
  `feeding_log` and `timezone`.
- **Dependencies**: none new in Python (`zoneinfo` is standard library); none new in the
  frontend.
- **Behaviour**: `generate_meal_plan` with no gap report and no logged entries is
  regression-tested to produce identical results to today.
- **Data / security**: still no database access and no identity. The backend recomputes
  every nutrient figure from the food table and never trusts client-supplied nutrients.

## Non-goals

- **Persisting the feeding log** (`feeding_log` table, migration, auth-scoped reads and
  writes) — Day 6, after Day 1 §7 and authentication. The tool and endpoint are written so
  that adding the row write is the only Day 6 change.
- **A learned or statistical prediction model for gaps** — [Stretch], explicitly excluded
  by §9b. Rolling averages only.
- **Push or in-app notifications when a gap is detected** — [Stretch] per §9b.
- **Nutrients beyond calories, protein, and iron in gap detection** — the three the planner
  targets; calcium and others are summed and displayed but not flagged.
- **Estimating breast-milk volume** — an unquantified breast-milk entry contributes no
  nutrients and marks its day incomplete; no imputation.
- **Meal logging as planned meals (the `meals`/`meal_items` tables)** — distinct from the
  feeding log per §9b and still deferred.
