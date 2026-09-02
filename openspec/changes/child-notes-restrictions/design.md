## Context

See proposal.md — Why. Relevant current state:

- `backend/models/child_profile.py`: `doctors_note` (Text) + `doctors_note_recorded_at`, CHECK
  `doctors_note_paired_with_timestamp`; relationships `allergies` (selectin), `feedings`,
  `growth_measurements` (cascade patterns). `backend/models/growth_measurement.py` and the
  migration `b2e7f1d1c002` are the newest table/migration patterns; the initial migration
  shows the enum-type lifecycle (`create_type=False`, create before tables, drop after).
- `backend/api/children.py:_apply` re-dates the note only when its text changed;
  `to_child_context` fills `ChildContext.doctors_note`; `get_targets` reports
  `doctors_note_present`.
- `backend/chat/router.py:PROFILE_FIELDS` lists `doctors_note` — every profile-backed argument
  is overwritten from the request's child; `_json_value` serialises scalars/enums only.
  `backend/chat/prompts.py:format_child_context` prints one `doctor's note:` line.
- `backend/tools/doctors_note.py`: `extract_override(note, model)` — one LLM call, JSON object
  or `null`, fence stripping in `_parse_override`, validated into `DoctorsNoteOverride
  {nutrient ∈ calories|protein|iron, direction, value, unit}`; `EXTRACT_SYSTEM_PROMPT` says
  food advice → null; `apply_override` decides conflict deterministically (5 % tolerance) and
  returns `OverrideOutcome`. `NoteExtraction {status: not_present|applied|no_numeric_target|
  unparsed, override, detail}`. Composed in `backend/tools/targets_resolution.py:resolve_targets`.
- `backend/tools/meal_plan.py:generate_meal_plan`: `resolve_targets` → `filter_by_diet` →
  `filter_foods` (safety; no bypass parameters) → `_compose` → `assert_plan_safe` → `_audit`
  (input snapshot includes raw `doctors_note`). `Exclusion {food_id, reasons}` renders under
  "Left out, and why". `MealPlanRequest` is `_Strict` (`extra="forbid"`) and has no exclusion
  field. `backend/tools/nutrient_gaps.py` and `backend/tools/feeding_log.py` also carry a
  singular `override`.
- `backend/nutrition/foods.py:LoadedFoodTable.resolve(query)` raises the same
  `FoodNotFoundError` for "ambiguous, here are the candidates" and for "unknown, here are
  difflib guesses" — verified: "no iron fortified oat cereal" hits the difflib path (because of
  "no"), while "iron fortified oat cereal" resolves uniquely. `FoodCategory` has 14 values;
  `backend/nutrition/diet.py:filter_by_diet` is the shape for a category-based exclusion step
  and never excludes milk feeds. "dairy" and "sugar" match no food.
- Frontend: `child-context-form.tsx` renders one Textarea; `child-context-store.ts` holds
  `doctors_note: string` (trim → null, `MAX_NOTE_CHARS` 4000); `meal-plan-card.tsx` shows one
  `OverrideBanner` when `plan.override.conflict`; `gap-report-card.tsx` reads
  `report.override`; `daily-targets.tsx` shows `TARGETS_NOTE_ON_FILE`; `api-types.ts`
  mirrors all of it; `copy.ts` has a snapshot test and forbids prose literals in components.
- Specs: `doctors-note-override` bounds extraction to nutrient/direction/value/unit ("SHALL
  NOT be used as free text downstream"); the Day 4 design's non-goal explicitly deferred
  food-level guidance.

## Goals / Non-Goals

**Goals:**
- A doctor's row can both set a nutrient target and leave foods out; a preference row can only
  leave foods out; the kind is a controlled vocabulary the parent chooses, not text the model
  infers.
- Every row ends with an outcome the parent can see; nothing is silently dropped.
- The model extracts phrases; code resolves, filters, and decides — no food id and no
  exclusion originates in the model.
- One Save on the Child tab, as today; the audit snapshot (hard rule 8) records the rows with
  their kinds and what each did.

**Non-Goals:**
- Anything under proposal.md — Non-goals. No change to the safety filter, the overridable
  nutrient set, or the chat SSE event order.

## Decisions

### 1. A `child_notes` table; notes travel inside the whole-profile write

**Decision:** `child_notes(id uuid7, child_profile_id FK CASCADE indexed, kind note_kind enum
{doctor, preference}, text Text CHECK btrim(text) <> '', position SmallInteger CHECK >= 0,
created_at)`. `ChildProfile.notes` relationship, `lazy="selectin"`, ordered by `(position,
created_at)`; the two profile columns and the paired CHECK are dropped. `ChildProfileWrite`
carries `notes: list[NoteRow]` (whole-profile replace, as every other field); the server diffs
by `(kind, text)`: an unchanged row keeps its id and `created_at` and takes its new position,
a removed row is deleted, a new row is inserted. Text length (≤ 500) and the row cap (20) are
Pydantic rules, not DB constraints, so the backfill of an existing note up to 4 000 characters
never truncates — an over-long backfilled line shows as a form error until shortened.

**Why:** One row per instruction is what "separate rows" means, and a kind column is what
keeps hard rule 3 doctor-only. Diffing inside the existing write keeps the single Save and the
existing dirty/draft mechanism untouched; separate CRUD routes would need a second save state.
No unique `(child, position)`: the set replace reorders rows within one unit of work and a
unique constraint would fail transiently.

**Alternative:** keep one text column split by lines with a prefix for kind — rejected: the
kind would be a text convention, unenforceable and easy to mistype.

### 2. Migration: enum + table, backfill one doctor row per line, reversible with stated loss

**Decision:** New revision (down `b2e7f1d1c002`): create `note_kind` (initial-migration
lifecycle), create `child_notes`, backfill with
`regexp_split_to_table(doctors_note, E'\r?\n') WITH ORDINALITY` — one `doctor` row per
non-blank line, `created_at = doctors_note_recorded_at`, position from the ordinal — then
drop the two columns and the CHECK. Downgrade: re-add the columns, `string_agg` the doctor
rows with `\n` ordered by position (`min(created_at)` as the timestamp), re-add the CHECK, drop
the table and the enum. The docstring states that preference rows and blank lines are lost on
downgrade. `tests/test_migrations.py` gains the split/join round-trip.

**Why:** Every existing note was written as a doctor's note, so `doctor` is the only honest
kind for the backfill; line splitting matches how parents already separated instructions.

### 3. `ChildContext.notes` replaces `doctors_note` everywhere

**Decision:** `NoteRow(_Strict) {kind: NoteKind, text: str (stripped, 1–500)}` defined once in
`backend/schemas/tools.py`; `ChildContext.notes: tuple[NoteRow, ...]` (≤ 20, no duplicate
`(kind, text)`), and the same field on `MealPlanRequest`, `GapDetectionRequest`,
`_ChildForTargets`, `ChildProfileWrite`. `PROFILE_FIELDS` swaps `doctors_note` for `notes`;
`_json_value` learns to dump models and sequences. `ChildProfileResponse.notes` is
`[{id, kind, text, recorded_at}]`; `DailyTargetsResponse` gets `doctor_notes_present` and
`preferences_present`.

**Why:** Every consumer already touches `doctors_note`, so the rename costs the same either
way, and typed rows are what per-row outcomes and the audit log need. A joined string plus a
side list would lose row identity.

### 4. One extraction call over all rows; the model extracts phrases, code resolves them

**Decision:** `extract_notes(notes, chat_model) -> NoteExtraction`. The human message numbers
the rows and tags each `[doctor]` or `[preference]`. The system prompt asks for
`{"rows": [{"row": n, "target": <object|null>, "avoid": [<phrase>, …]}, …]}`: `target` uses the
unchanged `DoctorsNoteOverride` vocabulary; `avoid` holds plain food or food-group phrases
with negation words stripped, food groups named from the fixed `FoodCategory` list. Envelope
validation failure → whole result `unparsed`. Per row, deterministic code then: validates
`target` (per-row issue on failure), drops a target on a `preference` row (issue), refuses two
`doctor` rows on one nutrient (both issues), de-duplicates and truncates phrases (≤ 80 chars,
≤ 10 per row). Result:

```
NoteTarget {note_index, override: DoctorsNoteOverride}
ExtractedAvoidance {note_index, phrase}
NoteIssue {note_index, detail}
NoteExtraction {status: not_present | applied | nothing_to_apply | unparsed,
                targets, avoid, issues, detail}
```
`no_numeric_target` becomes `nothing_to_apply` ("Avoid dairy" is now something to apply).
`apply_overrides(targets, overrides)` loops the existing `apply_override`; `resolve_targets`
returns `(targets, extraction, overrides: list[OverrideOutcome])` — an empty list means no
override, replacing today's placeholder outcome.

**Why:** The architecture principle: the model extracts structured inputs, code produces every
id and number. Refusing duplicate doctor targets rather than picking one keeps hard rule 3
honest — choosing silently would be a guess about a prescription. One call keeps cost and
latency as today.

### 5. Avoidance resolution: category first, then every matching food, never milk feeds

**Decision:** New `backend/nutrition/avoidance.py` (no LangChain import).
`CATEGORY_ALIASES`: every `FoodCategory` value, its spaced and plural forms, plus
`dairy products`/`milk products` → dairy; `nuts`/`seeds`/`nuts and seeds` → nut_seed;
`fats`/`oils` → fat_oil; `sweets`/`sugar`/`sweeteners` → sweetener;
`legumes`/`beans`/`pulses` → legume; `eggs` → egg; `grains` → grain — never `milk_feed`.
`LoadedFoodTable.matches(query) -> list[FoodItem]` (new): the exact id/name match alone, else
all token-subset candidates, else nothing (no difflib). `resolve_avoidance(item, kind, table)
-> Avoidance {note_index, kind, phrase, category|None, food_ids, applied, detail}`: a category
hit excludes every food in it; otherwise `matches(phrase)` minus milk feeds; only milk feeds
→ not applied with the milk-feed reason; nothing → not applied naming the phrase.
`filter_by_avoidances(foods, avoidances, reason_for)` mirrors `filter_by_diet` and collects
several reasons per food.

**Why:** "eggs" resolves to the single egg food but means the egg category; categories must
win first. Ambiguity is the safe direction for an avoidance: excluding all three apple entries
is visible under "Left out, and why", while guessing one could put the avoided food back on
the plate. Milk is a feeding-mode decision for the pediatrician, and the planner anchors every
plan on a milk feed (`MILK_FEED_PRIORITY`), so a note never removes it.

### 6. Planner: a deterministic avoidance step between diet and safety; outcomes per row

**Decision:** In `generate_meal_plan`: `avoidances = [resolve_avoidance(a, notes[a.note_index]
.kind, table) for a in extraction.avoid]`; `filter_by_avoidances` runs after `filter_by_diet`
and before `filter_foods`, so the safety filter and `assert_plan_safe` still see and check
the final list. Each excluded food becomes `Exclusion(food_id, reasons=[copy.note_exclusion_
reason(kind, text)])`. `_note_outcomes(notes, extraction, overrides, avoidances)` gives every
row `NoteOutcome {index, kind, text, applied, detail}`. `MealPlanResult.overrides` (list)
replaces `override`; `avoidances` and `note_outcomes` are added; `RemainingTargetsResult` and
`NutrientGapReport` carry `overrides`. Both audit snapshots record `notes` (rows with kinds),
`overrides`, `avoidances`, `note_outcomes`; the plan's `rules` gains `note_avoidances`.

**Why:** Order matters: a note can only narrow the candidate list, and the safety filter must
remain the last word. Per-row outcomes are what makes "shown as not applied" possible on
both the card and the Child tab.

### 7. Frontend: a row editor in the existing form; outcomes read from the latest plan

**Decision:** `ChildForm.notes: NoteRowDraft[] {key, kind, text}` (`key` client-only for
React lists; `fromProfile` uses the row id); `noteRowError` (blank, > 500, duplicate);
`toChildContext` emits trimmed rows or `errors.notes`. New `child-notes-fields.tsx` renders the
fieldset "Doctor's note and personal preferences": per row a kind Select, a text Input, a
Remove button; an "Add a row" button (disabled at 20). A new row defaults to `preference`.
`lib/note-outcomes.ts` walks the chat messages newest-first for the first meal-plan result
and returns its `note_outcomes`; the fieldset marks a row whose `(kind, text)` matches a
non-applied outcome; editing the text un-matches it. `meal-plan-card.tsx` renders one
`OverrideBanner` per conflicting override and a "Not applied, and why" section;
`gap-report-card.tsx` iterates `overrides`; `daily-targets.tsx` picks one of three disclosure
lines.

**Why:** The parent typed the row on the Child tab, so that is where a "not applied" mark is
actionable. Deriving it from the session's latest plan avoids a server-side outcome store and
an LLM call on save ([Stretch] both). Defaulting a new row to `preference` means a mislabelled
row can never change a target.

### 8. Copy: direct voice; reasons quote the row

**Decision:** Backend `copy.py`: `note_exclusion_reason(kind, text)` ("left out by your
doctor's note: “…”" / "left out by your preference: “…”"), `note_no_match(phrase)`,
`NOTE_MILK_FEED`, `NOTE_PREFERENCE_TARGET`, `note_duplicate_nutrient(label)`, `NOTE_NOTHING`,
`NOTE_EXTRACTION_UNAVAILABLE`; `FIELD_LABELS["notes"]`. Frontend `copy.ts`: `FORM_NOTES_LABEL`
("Doctor's note and personal preferences"), `FORM_NOTES_HINT`, `FORM_NOTE_PLACEHOLDER`,
`FORM_NOTES_ADD`, `FORM_NOTES_REMOVE`, `FORM_ERROR_NOTE` (500 chars, 20 rows, no duplicates),
`noteNotApplied(detail)`, `PLAN_NOT_APPLIED_TITLE` ("Not applied, and why"),
`TARGETS_NOTES_ON_FILE`, `TARGETS_DOCTOR_NOTE_ON_FILE`, `TARGETS_PREFERENCES_ON_FILE`. No
exclamation marks; a doctor's instruction is always in the direct voice.

## Risks / Trade-offs

- [Over-exclusion from an ambiguous phrase] → visible under "Left out, and why" with the row
  quoted; the parent can sharpen the row ("no raw apple").
- [Alias table misses a group the parent uses] → the row reads "not applied: not in our
  table"; aliases grow by review, not by the model.
- [Extraction refuses two doctor rows on one nutrient] → both rows say so and ask to keep
  one; deliberate over guessing.
- [Backfilled line over 500 characters] → shows as a validation error in the form until
  shortened; stated in the migration docstring; no data lost.
- [Downgrade loses preference rows] → stated; acceptable for a pre-production database.
- [Existing exact-equality audit tests] → updated to the new snapshot shape in the same
  change.
- [Two audit snapshots and three result models rename `override`] → one change, one commit;
  the frontend types move with it.

## Migration Plan

1. Apply backend and frontend together (the write API is breaking; the frontend and the
   evals harness — which carries no note — are the only clients).
2. `uv run alembic upgrade head` locally (backfills existing notes as doctor rows), then the
   full suites.
3. Deploy: `start.sh` runs the migration before uvicorn as today; the frontend ships in the
   same push.
4. Rollback: `alembic downgrade b2e7f1d1c002` re-joins doctor rows into the column (preference
   rows lost) and revert the commit.
