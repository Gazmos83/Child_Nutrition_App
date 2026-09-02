## MODIFIED Requirements

### Requirement: Missing or out-of-range measurements skip indicators, never fail the assessment

When length/height is not supplied the system SHALL compute weight-for-age only and SHALL
report the remaining indicators as skipped with a parent-facing reason naming the missing
measurement, worded so it reads correctly wherever the result is shown (the chat card or a
growth-log row) — it SHALL NOT refer to a particular screen location. When a supplied
length/height lies outside the range the WHO weight-for-length/height table covers, that
indicator SHALL be skipped with a reason stating the covered range; the other indicators
SHALL still be computed.

#### Scenario: No height supplied

- **WHEN** growth is assessed with age, sex, and weight but no length/height
- **THEN** the result contains weight-for-age and lists length/height-for-age,
  weight-for-length/height, and BMI-for-age as skipped, each with a reason naming the
  missing length or height and no screen location
- **AND** the assessment succeeds

#### Scenario: Length outside the table

- **WHEN** a 2-month-old's length is given as 40 cm
- **THEN** weight-for-length/height is skipped with a reason naming the covered range
- **AND** weight-for-age, length-for-age, and BMI-for-age are still computed
