## Why

The Day 6 growth assessment (`assess_growth`) places one snapshot — the profile's current
age, weight, and height — on the WHO 2006 growth standards, and its own card tells the
parent that the *trend* is what matters and that someone else must plot it. Nothing in the
app can: age is a hand-typed integer that goes stale every month, and editing weight or
height overwrites the old value without a trace. A parent who wants to see whether their
child is tracking along a percentile or drifting off it has nowhere to record the second
measurement. The archived growth-assessment change named both gaps as non-goals ("trend
analysis across measurements — needs stored history"; "age in days or a date of birth —
[Stretch]"); persistence has since shipped, so both are now cheap to close.

**Scope: [Stretch]. Post-MVP follow-on (Day 11 in the project's day numbering; the 7-day
plan is complete and deployed).** This closes the limitation the growth card discloses; it
adds no new tool, no new model call, and no new dependency.

## What Changes

- **Date of birth replaces the typed age** — **BREAKING** for the write API. The child
  profile stores `birth_date`; age in completed months is derived from it on every read
  (as of today for the profile, as of the measurement date for a growth row), so hard
  rule 1 still holds: every age the system stores, returns, or reasons with is a whole
  number of months, and nothing is ever kept in years. `ChildProfileWrite` takes
  `birth_date` and rejects `age_months`; `ChildProfileResponse` returns both `birth_date`
  and the derived `age_months`, so `ChildContext`, targets, prompts, and the tools are
  untouched. A birth date in the future or more than 60 months back is rejected. The
  migration backfills existing rows from `created_at − age_in_months` months.
- **A growth measurement log** — one row per child per calendar day: measured date, weight,
  optional length/height, owned through the child (hard rule 9), stored raw. Nothing
  derived is stored: each row's age in months and its WHO indicators are computed on read
  by the existing deterministic `assess_growth`, exactly as the feeding log prices feeds
  from the food table on read.
- **The newest measurement sets the profile** — posting a measurement dated on or after
  every existing one also updates the profile's weight and (when supplied) height, so
  daily targets and meal plans use the freshest numbers. Editing the profile form never
  creates a measurement row.
- **REST surface** — `GET`, `POST`, `DELETE` under `/api/children/{id}/growth`, all behind
  the owner check; same 404-as-absence stance for other accounts as the feeding log.
- **A fourth full-page tab, "Growth"** — add a measurement (date, weight, height), the list
  newest first with each measurement's percentile bars (the growth card's SD-track row,
  reused), the WHO source line and the existing direct-voice trend note. The Child tab's
  age field becomes a date-of-birth field with the derived age shown beside it.

## Capabilities

### New Capabilities

- `growth-tracking`: a per-child, owner-scoped log of dated weight and length/height
  measurements; each read returns the age in months at the measurement and its WHO
  assessment computed by arithmetic; the newest measurement synchronises the profile's
  weight and height; validation of measurement dates against the birth date and today.

### Modified Capabilities

- `child-profile`: "Age is represented in months" — age is derived from a stored date of
  birth rather than typed; the birth date may not be in the future and may not put the
  child past 60 months; the stored profile reproduces the chat context with the derived age.
- `chat-ui`: the child form takes a date of birth (showing the derived months) instead of a
  months field; the tabbed page gains a Growth tab with the measurement form, the
  newest-first list with percentile rows, and the trend note.
- `growth-assessment`: the no-height skip reason no longer points to "the side panel" (the
  same result now renders inside a growth-log row); it names the missing measurement in a
  location-neutral way.

## Impact

- **Database**: one new Alembic revision — `child_profiles.birth_date DATE NOT NULL` added
  with a backfill, `age_in_months` and its CHECK dropped; new table `growth_measurements`
  (UUIDv7 id, child FK with cascade, `measured_on DATE`, `weight_kg NUMERIC(5,2)`,
  `height_cm NUMERIC(4,1) NULL`, positivity CHECKs, unique `(child_profile_id, measured_on)`).
  Downgrade restores `age_in_months` from the birth date so `tests/test_migrations.py`
  still round-trips.
- **Backend**: `backend/models/child_profile.py` (+ new `growth_measurement.py`),
  `backend/schemas/child.py`, `backend/api/children.py` (three routes, derived-age
  helpers), `backend/api/chat.py` (one guarded call), new pure module
  `backend/nutrition/age.py` (completed-months arithmetic, stdlib only). No change to
  `backend/nutrition/growth.py`, `ChildContext`, the router's `PROFILE_FIELDS`, targets, or
  prompts. `backend/chat/copy.py`: one reworded string.
- **Frontend**: `child-context-store.ts` / `child-context-form.tsx` (birth date field),
  new `use-growth-log.ts`, `growth-tab.tsx`, `log-measurement-form.tsx`,
  `growth-log-store.ts`; `growth-card.tsx` exports its indicator row; `chat-page.tsx`
  adds the tab; `copy.ts` + snapshot; `api-types.ts`. No new npm dependency (native
  `<input type="date">`, existing `Progress`).
- **API contract**: **BREAKING** — `POST/PUT /api/children` require `birth_date` and
  refuse `age_months` (`extra="forbid"`); responses gain `birth_date`. The evals harness
  (`evals/harness/client.py:save_child`) needs a five-line adapter so `evals/cases.yaml`
  stays written in months. Chat SSE contract unchanged.
- **Dev data**: the dev database's eight profiles get backfilled birth dates that are
  accurate to within a month; no seeded measurement rows (the tab starts empty).
- **Security**: every new read and write goes through `OwnedChild`; hard rule 9 holds by
  construction. Nothing new reaches the language model.

## Non-goals

- **Charts** — a line chart against the WHO −2/median/+2 curves needs a charting library;
  the table-plus-percentile-bars view ships first. [Stretch]
- **Editing a measurement, same-day upsert, pagination of the list** — delete and re-add
  covers the MVP of this change; the list is bounded by one row per day. [Stretch]
- **Rolling the profile back on delete of the newest measurement** — the profile keeps its
  values; the tab discloses that the newest measurement sets them. [Stretch]
- **Per-user timezone** — "today" and completed months are computed on the UTC date with a
  one-day tolerance on writes; a local-date option is a later refinement. [Stretch]
- **Seeding a first measurement from the current profile** — a fabricated measurement date
  in a growth record is exactly the ambiguity the schema avoids; the tab's empty state
  invites the first real entry.
- **Exact-age (daily) WHO tables, gestational-age correction, head circumference, velocity
  standards** — unchanged from the growth-assessment change's non-goals.
- **Feeding percentiles or trends into nutrient targets** — a clinical judgement the
  disclaimer defers to the pediatrician.
