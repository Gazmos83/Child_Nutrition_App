## Context

See proposal.md — Why. Relevant current state:

- `backend/nutrition/targets.py:calculate_bmi` returns `BmiResult(bmi, weight_kg,
  height_cm, source, note)`; the note says the percentile "is not computed".
  `backend/tools/langchain_tools.py:build_tools()` binds the tools the router sees; its
  descriptions are what the model routes on. `tests/test_tools_langchain.py::EXPECTED_NAMES`
  pins the set.
- `backend/nutrition/foods.py` is the pattern for a committed reference table: whole-file
  Pydantic validation, an error naming the offending entry, `lru_cache` accessor plus a
  `reset_*_cache()` for tests. `backend/nutrition/` has no LangChain import (Day 4
  Decision 1).
- `backend/schemas/tools.py` holds `_AGE`, `_WEIGHT`, `_HEIGHT` field definitions,
  `MAX_HEIGHT_CM = 150`, `_Strict` inputs and `_Frozen` outputs; precision rule "kcal whole,
  g/mg one decimal, BMI two".
- `backend/models/enums.py:Sex` has two values and a docstring reserving it for growth
  lookups. `backend/chat/router.py:PROFILE_FIELDS` already fills `age_months`, `sex`,
  `weight_kg`, `height_cm` from the request's child context; a `None` context value pops
  the argument, so an optional field simply stays absent.
- `backend/chat/prompts.py` has `ROUTER_SYSTEM_PROMPT` (routing examples) and
  `ANSWER_WITH_TOOLS_SYSTEM_PROMPT` (numbers verbatim; override bullet; voice rules).
  `backend/chat/copy.py` / `frontend/src/lib/copy.ts` are the single copy sources (Day 5
  Decision 13).
- The frontend renders a tool result as a card when a type guard matches
  (`assistant-message.tsx` → `isMealPlanResult`); `Progress` primitives are installed.
- `knowledge-base/who-child-growth-standards-2006.md` carries WHO's cut-off table and the
  "trend over snapshot" guidance; `cdc-growth-charts-and-bmi.md` the CDC categories.
  The corpus is frozen for the Day 6 RAGAs baseline.
- WHO publishes per-indicator, per-sex z-score `.xlsx` tables with `L, M, S` columns by
  completed month (or by 0.1 cm of length/height) at
  `who.int/tools/child-growth-standards/standards/<indicator>` (BMI-for-age under
  `/toolkits/…`). URLs verified 2026-08-27.

## Goals / Non-Goals

**Goals:**
- A parent asking about BMI, percentile, or "is this normal for her age" gets sex- and
  age-specific WHO percentiles from table arithmetic, with reference values, in one tool
  call, and the card and prose read the way a careful clinician would say it to a parent.
- Reference data is auditable: anyone can rebuild the table from WHO's files and check
  the checksums.
- Zero change to any other tool's numbers; `calculate_bmi` keeps its contract.

**Non-Goals:**
- Exact-age (daily) tables, posture correction, CDC references, additional indicators,
  trend analysis, and feeding percentiles into targets — all listed in the proposal.
- Any RAG corpus edit.

## Decisions

### 1. A new tool `assess_growth`, not an extension of `calculate_bmi`

**Decision:** Add `assess_growth(age_months, sex, weight_kg, height_cm=None)`; leave
`calculate_bmi(weight_kg, height_cm)` as is except its note.

**Why:** `calculate_bmi`'s spec requirement is two inputs → one number; adding age and sex
would make them required for a call that does not need them, or optional with two
behaviours in one tool. A separate tool keeps each contract single-purpose and lets the
router's description say plainly which one answers "is this normal for her age".

**Alternative:** optional `age_months`/`sex` on `calculate_bmi` returning a percentile
when both are present — rejected for the dual behaviour and because BMI-for-age is only
one of the four indicators a parent's question usually needs.

### 2. WHO 2006 monthly LMS tables; four indicators; month 24 from the 2–5-year file

**Decision:** Use the WHO Child Growth Standards (2006) monthly tables for weight-for-age
(0–60), length/height-for-age (0–60), BMI-for-age (0–60), and the 0.1 cm tables for
weight-for-length (45–110 cm, under 24 months) and weight-for-height (65–120 cm, from 24
months). Where the 0–2 and 2–5 files overlap at month 24, take month 24 from the 2–5 file
(standing height). The form's single height field is read as recumbent length under 24
months and standing height from 24 months; WHO's 0.7 cm posture correction is not applied.

**Why:** WHO's range is the app's range, so one standard covers every child and the
citation is one line. Monthly rows match the age the form supplies (hard rule 1). The
overlap rule matches WHO's own convention for the 2–5 charts. Applying a posture
correction would require asking how the child was measured — a form change for a small
effect — so the result states the assumption instead (spec: "Age granularity is stated").

**Alternative:** WHO's expanded daily tables plus a date-of-birth field — more precise in
the first months, but a form and schema change; recorded as [Stretch] in the proposal.

### 3. Arithmetic in `backend/nutrition/growth.py`, stdlib only

**Decision:** `z = ((X / M) ** L − 1) / (L · S)` with WHO's tail adjustment for the
weight-based indicators (weight-for-age, weight-for-length/height, BMI-for-age): when
`z > 3`, `z = 3 + (X − SD3) / (SD3 − SD2)`; when `z < −3`, `z = −3 + (X − SD3neg) /
(SD2neg − SD3neg)`, where the SD values are derived from L, M, S. Length/height-for-age is
not adjusted (WHO applies none). Percentile = `statistics.NormalDist().cdf(z) × 100`. Round
z to two decimals and the percentile to one. No LangChain import in `backend/nutrition/`.

**Why:** This is WHO's published method (their `instructions-en.pdf`); `statistics.NormalDist`
removes any need for SciPy. Keeping it under `backend/nutrition/` keeps the
`grep -r langchain backend/nutrition` proof that no growth number touches the model.

**Alternative:** a third-party package (`pygrowup`-style) — adds a dependency whose data
version and licence would need auditing; the arithmetic is fifteen lines.

### 4. Height optional; indicators are skipped, not failed

**Decision:** `GrowthAssessmentInput.height_cm: float | None = None` (same bounds as
`_HEIGHT` when present). Without it the result has `indicators == [weight_for_age]` and
`skipped == [{indicator, reason}]` for the other three, `reason` from
`backend/chat/copy.py:GROWTH_NEEDS_HEIGHT`. A length/height outside the
weight-for-length/height table's range skips that indicator with
`GROWTH_HEIGHT_OUT_OF_RANGE` naming the covered range. The tool returns `status="ok"` in
both cases.

**Why:** Parents often know the weight and not the length. Failing the whole call would
turn a common case into a red ✗ chip and hide the one indicator that *can* be computed.
The existing missing-field hint path (`_validation_message`) still applies when the child
context is absent entirely, because `age_months`, `sex`, and `weight_kg` are required.
`resolve_context()` needs no change: a `None` height pops the argument.

### 5. Bands from the KB's WHO cut-offs; WHO label only where WHO defines one

**Decision:** `band` ∈ `well_below (< −3) / below (< −2) / expected / above (> +2) /
well_above (> +3)`. `who_label` is WHO's own term from the cut-off table already in
`knowledge-base/who-child-growth-standards-2006.md` (severely stunted / stunted; severely
underweight / underweight; severely wasted / wasted / overweight / obese) and `None` where
that table has "—" (weight-for-age above; length/height-for-age above). Each indicator
carries `reference {sd2neg, median, sd2pos}` computed from L, M, S.

**Why:** Tool output and the guideline text the RAG side cites must say the same thing
(hard rule 5). The `band` is what the UI colours and the prompt reasons about; the
`who_label` is quoted as WHO's word, which is what keeps the app from appearing to
diagnose. The reference triple lets the card show "WHO range for this age" without
another lookup.

**Alternative:** CDC percentile categories (5th/85th/95th) — CDC applies them from age 2
on CDC charts; mixing them with WHO curves would mislabel. Cited by RAG instead.

### 6. Reference data: generated YAML with provenance, loader mirrors `foods.py`

**Decision:** `scripts/build_growth_tables.py` downloads the eight WHO `.xlsx` files from
URLs pinned in the script, asserts the `L, M, S` columns and contiguous keys, applies the
month-24 rule, and writes `nutrition-data/who-growth-standards.yaml`:
`{version, source, source_url, retrieved, files: [{name, url, sha256}], tables:
{indicator: {female: [[key, L, M, S], …], male: […]}}}`. The script runs once with
`uv run --with openpyxl scripts/build_growth_tables.py`; the YAML is committed and is the
only thing the app reads. `backend/nutrition/growth.py:load_growth_table()` validates the
whole file with Pydantic (contiguous keys per table, `L, M, S` finite, `M > 0`, `S > 0`),
fails naming `indicator/sex/key`, and is cached with `get_growth_table()` /
`reset_growth_table_cache()`.

**Why:** Hand-typing ~2,400 rows is where a growth-chart feature goes wrong; a script with
checksums is reviewable and re-runnable. Keeping `openpyxl` ephemeral (`--with`) avoids a
runtime dependency for a one-off build; the lockfile stays untouched, as CLAUDE.md
requires. Whole-file validation is the same guarantee `foods.yaml` has: no partial table
ever serves a percentile.

**Alternative:** `uv add --dev openpyxl` — acceptable if the script is expected to run
often; not needed for a standard that changes on a decade scale.

### 7. Prompts: one routing example, one answer bullet, direct voice

**Decision:** `ROUTER_SYSTEM_PROMPT`'s child-number examples gain "growth percentile /
BMI / whether weight or length is normal for their age". `ANSWER_WITH_TOOLS_SYSTEM_PROMPT`
gains one bullet: state each indicator's percentile and z-score exactly as returned;
explain a WHO label only when the band is not `expected`, quoting it as WHO's term; for
skipped indicators say which measurement would unlock them; always note that one
measurement is a snapshot the pediatrician can plot over time; use the direct voice.
The tool description names "BMI", "percentile", and "growth chart" so the router prefers
it over `calculate_bmi` and over `search_guidelines` for a child-specific question.

**Why:** Day 5's check 7 routed a BMI question to the guideline search; the router only
sees descriptions and examples. Weight status is a safety-adjacent topic under Day 5
Decision 13, so the prose rule is explicit rather than left to the model's tone.

### 8. Frontend: `growth-card.tsx` behind a type guard; copy in `copy.ts`

**Decision:** `isGrowthAssessmentResult` in `api-types.ts`; `assistant-message.tsx` finds
the first matching tool result exactly as it does for the meal plan. The card shows one
row per indicator (label, measurement with unit, ordinal percentile, marker on a −3…+3
track built from `Progress`, reference line "WHO range for this age and sex: lo–hi unit,
median m", WHO label sentence when present), skipped rows with their reason, a source line,
and `GROWTH_TREND_NOTE`. Strings: `GROWTH_INDICATOR_LABELS`, `GROWTH_BAND_LABELS`,
`growthReference()`, `GROWTH_TREND_NOTE`, `growthWhoLabel()`, `TOOL_LABELS.assess_growth =
"Growth check"`; snapshot updated.

**Why:** The pattern exists and is tested; a card is what makes four percentiles readable.
Copy lives in one file so the snapshot test reviews every new sentence.

**Cut line:** if time runs short, ship without the card — the tool-activity chip already
renders the result JSON and the prose carries the numbers.

### 9. Sequencing and the tool-count scenario

**Decision:** Apply after `day-5-feeding-log-and-gaps` is archived. `EXPECTED_NAMES`
becomes eleven names. The change-2 delta's "Ten tools with typed schemas" scenario becomes
stale at that point; update that scenario's count in `openspec/specs/deterministic-nutrient-tools/spec.md`
as part of this change's archive (a one-word edit), rather than carrying a MODIFIED block
for a requirement that does not exist yet in the main spec.

**Why:** The change-2 requirement is only in a delta today; a MODIFIED delta here would
have nothing to match at archive time if change 2's tool task were cut and moved.

## Risks / Trade-offs

- [WHO URLs or `sfvrsn` query strings change] → the script pins full URLs and records
  sha256 per file; the committed YAML means the app never fetches at runtime. If a URL
  breaks, the script fails loudly and the last committed table stands.
- [Monthly rows vs. exact age] → in the first months growth is fast enough that a
  mid-month child can sit ~0.1–0.2 z from the daily value. The result note states the
  granularity; the prose repeats it; exact-age tables are the recorded [Stretch].
- [Misreading a percentile as a diagnosis] → WHO's label is quoted as WHO's term, only
  when outside the expected range; the trend note and the disclaimer ride on every
  answer; copy is direct and reviewed via the snapshot.
- [Model still calls `calculate_bmi` or `search_guidelines` for a growth question] →
  description and router example name the exact phrasings; end-to-end check repeats Day
  5's test 7. Both tools may legitimately run together; the card renders either way.
- [Posture correction omitted] → up to 0.7 cm bias in weight-for-length/height near 24
  months; stated in the note; the reference triple lets a parent see the margin.
- [Height outside table range for very short or tall children] → skipped with the covered
  range, other indicators still computed; no error chip.

## Migration Plan

Purely additive: new tool, new data file, new card. Rollback is removing the tool from
`build_tools()` and the card's type-guard branch; the YAML and module can stay. No
database, no API contract change.
