# doctors-note-override Specification

## Purpose

Turns a clinician's free-text note into a structured, bounded override that takes
precedence over the general nutrient target on conflict, and reports that conflict
explicitly rather than blending the two values.

## Requirements

### Requirement: Notes are extracted into a validated, bounded structure

When a doctor's note is present, the system SHALL extract it into a Pydantic-validated
structure naming the nutrient, the direction and value of the adjustment, and its unit.
The extraction SHALL NOT be used as free text anywhere downstream of this step (hard
rule 2's controlled-vocabulary spirit applied to derived values).

#### Scenario: A clear note is extracted

- **WHEN** a doctor's note states a specific nutrient limit or target for the child
- **THEN** the extracted structure names that nutrient and its value
- **AND** the structure passes validation before being used

#### Scenario: Extraction result is bounded

- **WHEN** a note is extracted
- **THEN** the resulting nutrient name is drawn from a fixed set of recognized nutrients
- **AND** an extraction naming a nutrient outside that set is rejected rather than passed
  through

### Requirement: Extraction failure degrades safely

If the note cannot be extracted (the language model is unavailable, or its output does
not validate), the system SHALL proceed using the general nutrient target and SHALL
flag that the note could not be applied, rather than blocking meal-plan generation or
silently ignoring the note without saying so.

#### Scenario: Extraction unavailable

- **WHEN** the language model call for note extraction fails
- **THEN** the meal plan is still generated using the general target
- **AND** the response indicates the note could not be applied

#### Scenario: Extraction result fails validation

- **WHEN** the language model's extraction does not match the expected structure
- **THEN** the general target is used
- **AND** the response indicates the note could not be applied

### Requirement: A validated override always wins on conflict

The system SHALL NOT compare a doctor's-note value against the general target using the
language model. When a validated override conflicts with the general nutrient target,
the system SHALL apply the override's value and SHALL report the conflict as an explicit
field on the result rather than blending or averaging the two values.

#### Scenario: Override applied on conflict

- **WHEN** a validated doctor's-note override specifies a lower calorie target than the
  general target for the child's age and weight
- **THEN** the meal plan uses the note's value
- **AND** the result reports that a conflict occurred and which source was used

#### Scenario: No conflict when values agree

- **WHEN** a validated override's value matches the general target within a defined
  tolerance
- **THEN** the result reports no conflict

#### Scenario: No note means no override

- **WHEN** a child's profile carries no doctor's note
- **THEN** the general nutrient target is used
- **AND** the result reports no conflict and no override

### Requirement: The overridable nutrient set is independent of the displayed set

The set of nutrients a doctor's note may override SHALL remain exactly calories, protein,
and iron, and SHALL NOT widen when the set of nutrients the system displays or tracks
widens. An extraction naming a nutrient that the system displays but does not accept for
override SHALL be rejected in the same way as any other unrecognized nutrient, and SHALL
degrade to "note not applied, flagged" rather than being silently dropped.

This boundary is stated explicitly because a wider displayed set invites the misreading
that anything displayed can be overridden. Widening it would mean asking the language model
to extract more units from free clinical text and would introduce interactions with
tolerable upper intake levels, for no user-visible gain.

#### Scenario: A note naming a displayed but non-overridable nutrient is rejected

- **WHEN** a doctor's note states a daily calcium limit, and calcium is among the nutrients
  displayed for the child
- **THEN** the extraction is rejected rather than applied
- **AND** the response flags that the note could not be applied, naming the reason
- **AND** the calcium target remains the general reference value

#### Scenario: The overridable set does not follow the displayed set

- **WHEN** the displayed target set is widened to include additional nutrients
- **THEN** the nutrients accepted for override are still exactly calories, protein, and iron

#### Scenario: An overridable nutrient still applies normally

- **WHEN** a doctor's note limits calories and the child's displayed set contains six
  nutrients
- **THEN** the calorie override is applied and the conflict is reported as before
- **AND** no other displayed nutrient's target is altered by the note
