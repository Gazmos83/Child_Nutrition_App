## Why

A parent wrote "no iron fortified oat cereal" in the doctor's note, asked "what should I feed
my kid today?", and got a plan that recommends iron-fortified infant oat cereal. That is the
documented behaviour, not a slip: the Day 4 design bounded note extraction to one numeric
nutrient target (calories, protein, or iron), told the model to return null for food advice,
and gave the planner no food-exclusion input. The note text is kept in the audit log and
nothing acts on it. The same single textarea also mixes a prescription with a household
preference ("we don't do pork") with no way to tell them apart — and hard rule 3 gives
precedence over nutrient targets to a *doctor's* instruction, not to a preference.

**Scope: [MVP-adjacent] follow-on to the Day 4 doctor's-note override and the Day 10 UI
(Day 11 in the project's numbering).** No new tool; one LLM extraction call as today; no new
dependency.

## What Changes

- **Notes become rows with a kind.** The profile carries zero or more note rows, each
  `doctor` or `preference`, one instruction per row (non-blank, at most 500 characters, at
  most 20 rows, no duplicates), stored in a new `child_notes` table with a recorded-at per
  row. The two note columns on the profile go away; the migration turns an existing note into
  doctor rows, one per line. **BREAKING** for the write API: `doctors_note` is replaced by
  `notes`.
- **Only doctor rows may change targets.** Numeric overrides are extracted from doctor rows
  only, one per nutrient across all rows; a target on a preference row is reported and not
  applied; two doctor rows on one nutrient are both refused rather than one silently chosen.
  The overridable set stays exactly calories, protein, and iron.
- **Foods and food groups to avoid are extracted and applied deterministically.** The model
  extracts the plain phrase ("iron fortified oat cereal", "dairy") with the negation stripped;
  code resolves it — a food category (with a small alias table: dairy products, nuts, beans,
  sweets…) first, else every table food the phrase names by the resolver's own token rule
  (an ambiguous phrase such as "apple" excludes every candidate: for an avoidance,
  under-excluding is the dangerous failure and over-excluding is visible). Breast milk and
  formula are never excluded by a note. The planner leaves the matched foods out before the
  safety filter, and lists them under "Left out, and why" with the row's own words.
- **Nothing is silently dropped.** Each row gets an outcome — applied or not, with the
  reason (no matching food, only a milk feed matched, a target on a preference row, two
  rows on one nutrient, extraction unavailable). The plan card shows "Not applied, and why";
  the Child tab marks a row the last plan could not apply. A plan is still generated.
- **UI**: the Child tab section becomes "Doctor's note and personal preferences" — a list
  of rows with a kind selector and a text field, add and remove, saved with the profile's
  single Save. The meal-plan card shows one banner per conflicting nutrient; the
  Daily-targets tab discloses doctor notes and preferences separately.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `child-profile`: the doctor's note becomes note rows with a kind; provenance per row;
  replace semantics per row; the audit and chat-context requirements name the rows.
- `doctors-note-override`: extraction covers every row, yields targets (doctor rows only)
  and avoidance phrases (both kinds) resolved by code; failure degrades per row; conflicts
  are reported per nutrient; a new requirement for deterministic avoidances that are always
  reported.
- `meal-plan-generation`: validated input carries note rows; every plan also reflects note
  avoidances from both kinds with the row as the reason; the audit snapshot records the
  rows, the overrides, the avoidances, and each row's outcome.
- `chat-ui`: the form's note field becomes rows with a kind; the card shows one banner per
  conflicting nutrient and lists rows that were not applied; the Child tab marks such rows;
  the Daily-targets disclosure distinguishes doctor notes from preferences.
- `intent-routing`: the note rows are among the profile-backed arguments the request fills;
  an empty list is authoritative.
- `observability`: the never-logged clause names the note rows and their kinds.

## Impact

- **Database**: new table `child_notes` and PostgreSQL enum `note_kind`; `child_profiles`
  loses `doctors_note`, `doctors_note_recorded_at`, and the paired CHECK; migration backfills
  and its downgrade re-joins doctor rows (preference rows are lost on downgrade, stated).
- **Backend**: `backend/models/{enums,child_note,child_profile}.py`,
  `backend/schemas/{tools,chat,child}.py`, `backend/api/children.py`,
  `backend/tools/{doctors_note,targets_resolution,meal_plan,nutrient_gaps,feeding_log,langchain_tools}.py`,
  new `backend/nutrition/avoidance.py`, `backend/nutrition/foods.py` (`matches`),
  `backend/chat/{router,prompts,copy}.py`. Audit snapshots gain `notes`, `overrides`,
  `avoidances`, `note_outcomes`.
- **Frontend**: `child-context-store.ts`, `child-context-form.tsx`, new
  `child-notes-fields.tsx`, `meal-plan-card.tsx`, `gap-report-card.tsx`, `daily-targets.tsx`,
  `chat-page.tsx`, `api-types.ts`, `enums.ts` + fixture, `copy.ts` + snapshot, new
  `lib/note-outcomes.ts`.
- **API contract**: **BREAKING** — `ChildProfileWrite.notes` replaces `doctors_note`;
  `ChildProfileResponse.notes`; `DailyTargetsResponse.doctor_notes_present` and
  `preferences_present` replace `doctors_note_present`; `MealPlanResult.overrides` (list)
  replaces `override`, plus `avoidances` and `note_outcomes`; `NutrientGapReport.overrides`
  and `RemainingTargetsResult.overrides` likewise; `NoteExtraction` reshaped. The frontend and
  the evals harness (which carries no note) are the only clients.
- **Security**: every read and write stays behind `OwnedChild`; nothing new reaches the model
  except the rows it already saw as one text.

## Non-goals

- Instructions about milk feeds ("switch to formula", "no breast milk") — never applied by a
  note; the row says so and points to the pediatrician. [Stretch]
- Synonyms beyond the small category alias table ("courgette", brand names). [Stretch]
- Storing a row's last outcome server-side — the Child-tab badge derives from the latest plan
  in the chat session. [Stretch]
- An LLM call on save to pre-validate rows — extraction happens when a plan is made.
- Widening the overridable nutrient set — unchanged, exactly calories, protein, iron.
