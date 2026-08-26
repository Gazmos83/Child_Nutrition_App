## Purpose

`generate_meal_plan()`, the core child-facing tool: composes a nutrient target, foods
filtered by diet preference and allergens, the doctor's-note override, and the
infant-safety filter into one recommendation, logged for auditability and carrying the
not-medical-advice disclaimer.

## ADDED Requirements

### Requirement: A meal plan is built only from validated child input

`generate_meal_plan` SHALL accept a Pydantic-validated child input (age in months,
weight, height, sex, diet preference, allergies, optional doctor's note) and SHALL NOT
read a stored profile from a database (no user-scoped read exists yet; hard rule 9 is
satisfied by not touching user data until authentication ships).

#### Scenario: Valid input produces a plan

- **WHEN** `generate_meal_plan` is called with a valid child input
- **THEN** a meal plan is returned

#### Scenario: Invalid input is rejected before any generation

- **WHEN** `generate_meal_plan` is called with an age outside 0–60 months
- **THEN** the call is rejected before any nutrient calculation, food filtering, or
  language-model call occurs

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
generated the way it was (hard rule 8).

#### Scenario: Log captures the full snapshot

- **WHEN** a meal plan is generated
- **THEN** a log record is emitted containing the child's age, weight, height, sex, diet
  preference, allergy set, doctor's note (if any), and the source of each nutrient
  target used

#### Scenario: Logging happens even when no plan can be produced

- **WHEN** the safety filter leaves no eligible foods
- **THEN** the input snapshot is still logged, alongside the no-safe-plan result
