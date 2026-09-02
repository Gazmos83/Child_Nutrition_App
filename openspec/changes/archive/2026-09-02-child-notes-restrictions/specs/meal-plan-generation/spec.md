## MODIFIED Requirements

### Requirement: A meal plan is built only from validated child input

`generate_meal_plan` SHALL accept a Pydantic-validated child input (age in months,
weight, height, sex, diet preference, allergies, note rows with their kinds), and MAY
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

#### Scenario: Malformed note rows are rejected before any generation

- **WHEN** `generate_meal_plan` is called with a blank note row or a row of an unknown kind
- **THEN** the call is rejected before any calculation or language-model call

### Requirement: Every plan reflects diet preference, allergies, the safety filter, and any doctor's-note override

The system SHALL exclude foods that conflict with the child's diet preference (e.g. no
meat or fish for a vegan child), exclude foods containing a recorded allergen, leave out
the foods and food groups the note rows say to avoid (both `doctor` and `preference` rows,
resolved by the `doctors-note-override` capability) with the row as the stated reason,
apply the infant-safety filter (`infant-safety-filter` capability), and apply the
doctor's-row overrides (`doctors-note-override` capability) before returning a plan.

#### Scenario: Diet preference respected

- **WHEN** a meal plan is generated for a vegan child
- **THEN** no animal-derived food appears in the plan

#### Scenario: All four constraints compose

- **WHEN** a meal plan is generated for a child with an allergy, a non-omnivore diet
  preference, an age under 12 months, and a doctor row with a conflicting target
- **THEN** the returned plan excludes the allergen and diet-incompatible foods, excludes
  every food the safety filter forbids for that age, and uses the doctor's-row value
  where it conflicts with the general target

#### Scenario: A note avoidance appears under exclusions with its row as the reason

- **WHEN** a meal plan is generated for a child whose preference row reads "no pork"
- **THEN** no pork appears in the plan
- **AND** the exclusions name the pork entry with a reason quoting the row and its kind

### Requirement: Every meal-plan generation is logged with its full input snapshot

The system SHALL log, for every `generate_meal_plan` call, the full input snapshot (age,
weight, height, sex, diet preference, allergies, the note rows with their kinds if any, and
which rule or source produced each target) sufficient to reconstruct why the plan was
generated the way it was (hard rule 8), and SHALL additionally record the gap report
(status, confidence, days, flags), the identifiers and timestamps of the day's logged
entries with their summed nutrients, each adjustment the plan made because of them, the
overrides applied, the avoidances resolved, and each row's outcome. When the plan is
generated inside a request, the record SHALL carry that request's correlation identifier,
the account identifier, and the stored child profile identifier the inputs came from, so
the recommendation can be traced to the account and profile that received it.

#### Scenario: Log captures the full snapshot

- **WHEN** a meal plan is generated
- **THEN** a log record is emitted containing the child's age, weight, height, sex, diet
  preference, allergy set, note rows with kinds (if any), and the source of each nutrient
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

#### Scenario: Log records what each row did

- **WHEN** a plan is generated for a profile with note rows
- **THEN** the log record lists the overrides applied, the avoidances with the foods they
  excluded, and each row's outcome with its reason
