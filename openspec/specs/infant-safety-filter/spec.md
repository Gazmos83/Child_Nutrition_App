# infant-safety-filter Specification

## Purpose

A hard-coded safety check, independent of the RAG and LLM pipeline, that every candidate
food and every generated meal plan passes through — so that no unsafe recommendation can
reach a parent regardless of what the language model produces or is told to produce.

## Requirements

### Requirement: The filter runs independently of the language model

The safety filter SHALL be implemented as deterministic code with no dependency on the
language model or the RAG pipeline, and SHALL run on every meal plan unconditionally.
Nothing in a prompt, tool call, or model output SHALL be able to skip or weaken it.

#### Scenario: Filter runs regardless of model output

- **WHEN** a meal plan is generated
- **THEN** the safety filter executes as part of that generation
- **AND** its result is not conditioned on any text the language model produced

#### Scenario: No override path exists

- **WHEN** the system is inspected for a way to bypass the safety filter (a flag,
  parameter, or prompt instruction)
- **THEN** no such path exists — the filter always runs

### Requirement: No honey under 12 months

The system SHALL exclude any food flagged as containing honey from a meal plan for a
child under 12 months.

#### Scenario: Honey excluded for a 9-month-old

- **WHEN** a meal plan is generated for a 9-month-old and a honey-containing food is
  among the candidates
- **THEN** that food does not appear in the plan

#### Scenario: Honey permitted from 12 months

- **WHEN** a meal plan is generated for a 12-month-old
- **THEN** a honey-containing food may appear in the plan

### Requirement: No recognized choking hazards under 4 years

The system SHALL exclude any food flagged as a choking hazard from a meal plan for a
child under 48 months.

#### Scenario: Choking hazard excluded for a toddler

- **WHEN** a meal plan is generated for a 2-year-old and a food flagged as a choking
  hazard (e.g. whole grapes, whole nuts, popcorn) is among the candidates
- **THEN** that food does not appear in the plan

### Requirement: No commonly-unpasteurized products

The system SHALL exclude any food flagged as commonly served unpasteurized from every
meal plan regardless of the child's age.

#### Scenario: Unpasteurized product excluded

- **WHEN** a meal plan is generated and a food flagged as commonly unpasteurized is
  among the candidates
- **THEN** that food does not appear in the plan for any age within 0–60 months

### Requirement: No recorded allergen

The system SHALL exclude any food containing an allergen recorded against the child from
every meal plan.

#### Scenario: Allergen excluded

- **WHEN** a meal plan is generated for a child recorded with a peanut allergy
- **THEN** no food flagged as containing peanut appears in the plan

### Requirement: A plan with no safe candidates is reported, not silently emptied

When the safety filter (combined with diet-preference and allergen filtering) leaves no
eligible foods, the system SHALL report that no safe plan could be generated rather than
returning an empty or partial plan without explanation.

#### Scenario: No eligible foods

- **WHEN** every candidate food is excluded by the safety filter or the child's allergies
- **THEN** the tool reports that no safe meal plan could be generated
- **AND** does not return a plan containing zero items without that explanation
