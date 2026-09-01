# meal-plan-generation Specification

## Purpose

`generate_meal_plan()`, the core child-facing tool: composes a nutrient target, foods
filtered by diet preference and allergens, the doctor's-note override, and the
infant-safety filter into one recommendation, logged for auditability and carrying the
not-medical-advice disclaimer.

## Requirements

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

### Requirement: Every plan reflects diet preference, allergies, the safety filter, and any doctor's-note override

The system SHALL exclude foods that conflict with the child's diet preference (e.g. no
meat or fish for a vegan child), exclude foods containing a recorded allergen, apply the
infant-safety filter (`infant-safety-filter` capability), and apply the doctor's-note
override (`doctors-note-override` capability) before returning a plan.

#### Scenario: Diet preference respected

- **WHEN** a meal plan is generated for a vegan child
- **THEN** no animal-derived food appears in the plan

#### Scenario: All four constraints compose

- **WHEN** a meal plan is generated for a child with an allergy, a non-omnivore diet
  preference, an age under 12 months, and a doctor's note with a conflicting target
- **THEN** the returned plan excludes the allergen and diet-incompatible foods, excludes
  every food the safety filter forbids for that age, and uses the doctor's-note value
  where it conflicts with the general target

### Requirement: Every plan carries the not-medical-advice disclaimer

The system SHALL attach the fixed not-medical-advice disclaimer to every generated meal
plan, matching the disclaimer already used by the RAG answering capability.

#### Scenario: Disclaimer present

- **WHEN** any meal plan is generated
- **THEN** the response includes the not-medical-advice disclaimer

### Requirement: Every meal-plan generation is logged with its full input snapshot

The system SHALL log, for every `generate_meal_plan` call, the full input snapshot (age,
weight, height, sex, diet preference, allergies, doctor's note text if present, and which
rule or source produced each target) sufficient to reconstruct why the plan was
generated the way it was (hard rule 8), and SHALL additionally record the gap report
(status, confidence, days, flags), the identifiers and timestamps of the day's logged
entries with their summed nutrients, and each adjustment the plan made because of them.
When the plan is generated inside a request, the record SHALL carry that request's
correlation identifier, the account identifier, and the stored child profile identifier
the inputs came from, so the recommendation can be traced to the account and profile that
received it.

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

#### Scenario: Log record is correlated to account and profile

- **WHEN** a plan is generated through the chat for a signed-in parent's saved child
- **THEN** the log record carries the request id, the account id, and the child profile id

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

### Requirement: The targets a plan reports are wider than the set it composes toward

A meal plan SHALL report the child's full displayed target set, so that the plan's audit
record and the parent-facing response account for every nutrient the system shows for that
child (hard rule 8). The system SHALL compose the plan against calories, protein, and iron
only. A nutrient that is reported but not composed against SHALL NOT influence food
selection, serving sizes, or the plan's outcome, and SHALL NOT cause a plan to be reported
as failing to meet its targets.

This distinction is deliberate: widening the reported set improves auditability, while
widening the composed-against set would change a greedy multi-objective fill whose
behaviour is pinned by regression fixtures.

#### Scenario: A reported nutrient does not steer composition

- **WHEN** two plans are generated for the same child, one with calcium in the displayed
  target set and one without, all other inputs identical
- **THEN** both plans contain the same items with the same servings
- **AND** both report the same outcome

#### Scenario: A plan is not failed by a nutrient it does not compose toward

- **WHEN** a plan meets its calorie, protein, and iron targets while falling short of a
  reported calcium target
- **THEN** the plan's outcome reflects that its calorie, protein, and iron targets are met
- **AND** the shortfall is not reported as a composition failure

#### Scenario: The audit record covers the reported set

- **WHEN** a plan is generated for a vegan child
- **THEN** the audit record names every nutrient in the child's displayed target set,
  each with the value and source used
- **AND** it records that the composed-against set was calories, protein, and iron
