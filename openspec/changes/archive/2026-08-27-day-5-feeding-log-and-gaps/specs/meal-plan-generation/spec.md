## MODIFIED Requirements

### Requirement: A meal plan is built only from validated child input

`generate_meal_plan` SHALL accept a Pydantic-validated child input (age in months,
weight, height, sex, diet preference, allergies, optional doctor's note), and MAY
additionally accept an optional nutrient-gap report and the child's feeding entries for
the current day. It SHALL NOT read a stored profile or log from a database (no user-scoped
read exists yet; hard rule 9 is satisfied by not touching user data until authentication
ships). With no gap report and no entries, the plan SHALL be identical to the plan
produced without these inputs.

#### Scenario: Valid input produces a plan

- **WHEN** `generate_meal_plan` is called with a valid child input
- **THEN** a meal plan is returned

#### Scenario: Invalid input is rejected before any generation

- **WHEN** `generate_meal_plan` is called with an age outside 0–60 months
- **THEN** the call is rejected before any nutrient calculation, food filtering, or
  language-model call occurs

#### Scenario: No log inputs, unchanged output

- **WHEN** `generate_meal_plan` is called with the same child input as before this change,
  no gap report, and no entries
- **THEN** the returned plan is identical to the plan produced before this change

### Requirement: Every meal-plan generation is logged with its full input snapshot

The system SHALL log, for every `generate_meal_plan` call, the full input snapshot (age,
weight, height, sex, diet preference, allergies, doctor's note text if present, and which
rule or source produced each target) sufficient to reconstruct why the plan was
generated the way it was (hard rule 8), and SHALL additionally record the gap report
(status, confidence, days, flags), the identifiers and timestamps of the day's logged
entries with their summed nutrients, and each adjustment the plan made because of them.

#### Scenario: Log captures the full snapshot

- **WHEN** a meal plan is generated
- **THEN** a log record is emitted containing the child's age, weight, height, sex, diet
  preference, allergy set, doctor's note (if any), and the source of each nutrient
  target used

#### Scenario: Logging happens even when no plan can be produced

- **WHEN** the safety filter leaves no eligible foods
- **THEN** the input snapshot is still logged, alongside the no-safe-plan result

#### Scenario: Log names what informed an adjustment

- **WHEN** a plan is generated with a gap report and logged entries
- **THEN** the log record includes the gap report's status, confidence, days and flags,
  the logged entries' identifiers and summed nutrients, and the adjustments applied

## ADDED Requirements

### Requirement: Gaps steer composition without raising targets

When a gap report flags a nutrient `below` with confidence `medium` or `high`, the system
SHALL prefer foods dense in that nutrient when composing the plan and SHALL record the
adjustment. The system SHALL NOT raise any nutrient target above the reference value
because of a gap, SHALL keep every upper intake limit in force, and SHALL treat
`low`-confidence flags as informational only.

#### Scenario: Medium-confidence protein gap changes food choice

- **WHEN** the gap report flags protein `below` at `medium` confidence
- **THEN** the plan's food selection favours protein-dense eligible foods, the plan's
  adjustments name protein, and the calorie, protein, and iron targets equal the reference
  values

#### Scenario: Low-confidence gap changes nothing

- **WHEN** the gap report flags iron `below` at `low` confidence
- **THEN** the plan is identical to the plan without the report, and the report is
  surfaced as informational

#### Scenario: Upper limit still enforced

- **WHEN** iron is flagged `below` at `high` confidence
- **THEN** no serving is added that would push iron past the tolerable upper intake level

### Requirement: Today's intake is subtracted so the plan covers the rest of the day

When the current day's entries are supplied, the system SHALL subtract their summed
nutrients from the targets (floored at zero) before composing, SHALL report the
already-logged totals, and SHALL return the outcome `targets_met` with no items when
remaining calories are below ten percent of the calorie target. The infant-safety filter
and doctor's-note override SHALL run unchanged.

#### Scenario: Partial day

- **WHEN** entries totalling 300 kcal are supplied for a child with a 750 kcal target
- **THEN** the plan composes toward about 450 kcal, reports 300 kcal already logged, and
  still passes the safety filter

#### Scenario: Targets already met

- **WHEN** entries totalling 720 kcal are supplied for a child with a 750 kcal target
- **THEN** the outcome is `targets_met`, the plan has no items, the message says so, and
  the disclaimer is present

#### Scenario: Override still wins

- **WHEN** the doctor's note limits calories to 650 kcal and 300 kcal has been logged
- **THEN** the plan composes toward 350 kcal and reports the override conflict
