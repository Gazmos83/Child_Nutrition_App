## ADDED Requirements

### Requirement: `assess_growth` joins the deterministic tool set

The system SHALL expose `assess_growth` as a deterministic tool with a typed, validated
input (age in months, sex, weight, optional length/height), subject to the same
requirements as the existing tools: no language-model arithmetic, validation before
computation, and results that carry their source. Its behaviour is specified by the
`growth-assessment` capability.

#### Scenario: Tool present with a typed schema

- **WHEN** the tool set is built
- **THEN** it contains `assess_growth` alongside the existing tools, with a typed argument
  schema that marks length/height optional

#### Scenario: Invalid input rejected before computation

- **WHEN** `assess_growth` is invoked with a sex value outside the vocabulary
- **THEN** the invocation is rejected by validation and no lookup runs

#### Scenario: No model call

- **WHEN** `assess_growth` is invoked
- **THEN** no language-model call is made

## MODIFIED Requirements

### Requirement: `calculate_bmi` computes BMI from weight and height

The system SHALL compute BMI as weight in kilograms divided by height in metres
squared, given as call parameters rather than read from a stored profile. The result
SHALL state that a child's BMI is interpretable only as an age- and sex-specific
percentile and SHALL direct the reader to `assess_growth` for it.

#### Scenario: BMI computed from valid inputs

- **WHEN** `calculate_bmi` is called with a positive weight in kilograms and a positive
  height in centimetres
- **THEN** the returned BMI equals weight_kg / (height_m ^ 2), rounded to two decimal
  places

#### Scenario: Result points to the percentile tool

- **WHEN** `calculate_bmi` returns
- **THEN** its note names `assess_growth` as the way to obtain the percentile
