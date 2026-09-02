## MODIFIED Requirements

### Requirement: Notes are extracted into a validated, bounded structure

When a profile carries note rows, the system SHALL extract them, in one pass over all rows,
into a Pydantic-validated structure: for each row, at most one numeric nutrient target
naming the nutrient, the direction and value of the adjustment, and its unit; and the plain
phrases of any foods or food groups the row says to avoid. Targets SHALL be taken only from
`doctor` rows; a target found on a `preference` row SHALL be reported and not applied. At
most one target per nutrient SHALL be applied across all rows; when two `doctor` rows name
the same nutrient, neither SHALL be applied and both SHALL be reported. Avoidance phrases
SHALL be resolved to table foods or food categories by deterministic code and SHALL NOT be
used as free text anywhere downstream of this step (hard rule 2's controlled-vocabulary
spirit applied to derived values).

#### Scenario: A clear note is extracted

- **WHEN** a `doctor` row states a specific nutrient limit or target for the child
- **THEN** the extracted structure names that nutrient and its value for that row
- **AND** the structure passes validation before being used

#### Scenario: Extraction result is bounded

- **WHEN** a row is extracted
- **THEN** the resulting nutrient name is drawn from a fixed set of recognized nutrients
- **AND** an extraction naming a nutrient outside that set is rejected for that row rather
  than passed through, while other rows are still applied

#### Scenario: A food to avoid is extracted as a phrase

- **WHEN** a row reads "no iron fortified oat cereal"
- **THEN** the extracted structure carries the phrase "iron fortified oat cereal" for that
  row, with no target

#### Scenario: A preference row's target is refused

- **WHEN** a `preference` row states "limit calories to 600 kcal"
- **THEN** no target is applied from it
- **AND** the row is reported as not applied, naming that only a doctor's row can change a
  target

#### Scenario: Two doctor rows on one nutrient are both refused

- **WHEN** two `doctor` rows each state a calorie limit
- **THEN** neither is applied and both rows are reported, asking to keep one

### Requirement: Extraction failure degrades safely

If the rows cannot be extracted (the language model is unavailable, or its output does
not validate), the system SHALL proceed using the general nutrient targets and no
avoidances, and SHALL flag every row as not applied, rather than blocking meal-plan
generation or silently ignoring the rows without saying so. When one row's extracted target
fails validation, only that row SHALL be reported as not applied.

#### Scenario: Extraction unavailable

- **WHEN** the language model call for note extraction fails
- **THEN** the meal plan is still generated using the general targets
- **AND** the response indicates that every row could not be applied

#### Scenario: Extraction result fails validation

- **WHEN** the language model's extraction does not match the expected structure
- **THEN** the general targets are used
- **AND** the response indicates the rows could not be applied

### Requirement: A validated override always wins on conflict

The system SHALL NOT compare a doctor's-row value against the general target using the
language model. When a validated override conflicts with the general nutrient target,
the system SHALL apply the override's value and SHALL report the conflict as an explicit
entry on the result, one per nutrient, rather than blending or averaging the two values.

#### Scenario: Override applied on conflict

- **WHEN** a validated doctor's-row override specifies a lower calorie target than the
  general target for the child's age and weight
- **THEN** the meal plan uses the row's value
- **AND** the result reports that a conflict occurred and which source was used

#### Scenario: No conflict when values agree

- **WHEN** a validated override's value matches the general target within a defined
  tolerance
- **THEN** the result reports no conflict for that nutrient

#### Scenario: No note means no override

- **WHEN** a child's profile carries no note rows
- **THEN** the general nutrient targets are used
- **AND** the result reports no overrides

#### Scenario: Two nutrients overridden independently

- **WHEN** one `doctor` row limits calories and another sets an iron target, both
  conflicting with the general values
- **THEN** the result reports two conflicts, one per nutrient, and no other target changes

## ADDED Requirements

### Requirement: Food and category avoidances are applied deterministically and reported

For each extracted avoidance phrase the system SHALL, in code, first try to match a food
category (its name, plural, or a fixed alias such as "dairy products", "nuts", "beans",
"sweets"), and otherwise match every table food the phrase names under the food table's
own whole-word rule; an ambiguous phrase SHALL exclude every candidate it matches. Breast
milk and formula SHALL never be excluded by a note. The matched foods SHALL be left out of
the plan before the safety filter runs and SHALL appear among the plan's exclusions with the
row's kind and text as the reason. A phrase that matches nothing, or only milk feeds, SHALL
be reported as not applied with the reason; every row SHALL carry an outcome (applied or
not, with a reason) and the plan SHALL still be generated.

#### Scenario: A named food is left out

- **WHEN** a `doctor` row reads "no iron fortified oat cereal" and the table's
  iron-fortified infant oat cereal would otherwise be planned
- **THEN** the plan contains no iron-fortified infant cereal
- **AND** the exclusions list it with the row's text as the reason
- **AND** the row's outcome is applied

#### Scenario: A food group is left out but milk feeds stay

- **WHEN** a `preference` row reads "avoid dairy" for an 8-month-old
- **THEN** no food of the dairy category is planned
- **AND** the milk feed (breast milk or formula) is still planned

#### Scenario: An ambiguous phrase excludes every candidate

- **WHEN** a row reads "no apple" and the table holds a cooked-apple, a raw-apple-chunks,
  and an unpasteurized-juice entry
- **THEN** all three are left out and listed with the row as the reason

#### Scenario: An unknown phrase is reported, not dropped

- **WHEN** a row reads "no kale chips" and the table has no such food or group
- **THEN** the plan is generated
- **AND** the row's outcome is not applied, saying the food or group is not in the table

#### Scenario: A milk feed cannot be avoided by a note

- **WHEN** a row reads "no breast milk"
- **THEN** the milk feed stays in the plan
- **AND** the row's outcome is not applied, saying milk feeds are never left out by a note

#### Scenario: A phrase naming both dairy foods and a milk feed keeps the milk feed

- **WHEN** a row reads "no milk"
- **THEN** cow's milk and the other dairy foods it names are left out
- **AND** the milk feed stays and the row's outcome says milk feeds are never left out by a note
