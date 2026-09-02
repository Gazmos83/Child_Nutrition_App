## MODIFIED Requirements

### Requirement: Request-supplied child context is authoritative for tool arguments

When the request carries child context, the system SHALL fill every profile-backed tool
argument (age in months, weight, sex, height, allergies, diet preference, note rows with
their kinds, activity level) from that context, SHALL replace any conflicting value proposed
by the model — an empty list of note rows included, so the model can never add a row — and
SHALL record which arguments were taken from the context. Ages SHALL be in months (hard
rule 1); allergies, diet preference, and note kinds SHALL be controlled-vocabulary values
(hard rule 2).

#### Scenario: Model-proposed weight is overridden

- **WHEN** the child context says 8.5 kg and the model proposes `weight_kg = 9`
- **THEN** the tool runs with 8.5 kg and the tool activity lists `weight_kg` as taken from
  the child context

#### Scenario: Missing context is reported, not guessed

- **WHEN** no child context is supplied and the model proposes a tool call lacking a
  required argument
- **THEN** the tool is not run with invented values; the tool activity reports a validation
  error with a warm, direct message pointing the parent to the side panel and what to fill
  in — it names the missing information, never "a missing child"

#### Scenario: Off-vocabulary allergy is rejected

- **WHEN** the request's child context names an allergy outside the controlled vocabulary
- **THEN** the request is rejected before routing with a validation error

#### Scenario: Model-proposed note rows are discarded

- **WHEN** the child context carries no note rows and the model proposes a tool call with a
  row "no vegetables"
- **THEN** the tool runs with an empty list of rows and the activity lists the rows as taken
  from the child context
