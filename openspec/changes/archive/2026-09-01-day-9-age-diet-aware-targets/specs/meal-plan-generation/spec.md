## ADDED Requirements

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
