# growth-assessment Specification

## Purpose

Places a child's weight, length/height, and BMI on the WHO Child Growth Standards for their
age in months and sex, returning z-scores, percentiles, and WHO cut-off bands with the
reference values and provenance a parent and the answer prompt can rely on.

## Requirements

### Requirement: Growth is assessed against sex- and age-specific WHO standards by arithmetic only

Given a child's age in completed months (0–60), sex, weight in kilograms, and optionally
length/height in centimetres, the system SHALL compute, for each indicator it can, the
z-score and percentile against the WHO Child Growth Standards (2006) for that sex and age,
using the published LMS parameters and deterministic arithmetic. No value SHALL come from
the language model, and identical inputs SHALL produce identical results. Every result
SHALL name the standard and its publication year (hard rule 5).

#### Scenario: Girls and boys differ

- **WHEN** growth is assessed for an 8-month-old girl and an 8-month-old boy with the same
  weight and length
- **THEN** the two results have different z-scores and percentiles for every indicator

#### Scenario: The median is the 50th percentile

- **WHEN** a child's weight equals the WHO median weight-for-age for their sex and age
- **THEN** the weight-for-age z-score is 0.00 and the percentile is 50.0

#### Scenario: Repeated calls are identical

- **WHEN** growth is assessed twice with the same inputs
- **THEN** both results are equal

#### Scenario: Source carried on the result

- **WHEN** any growth assessment is returned
- **THEN** it names the WHO Child Growth Standards and the year 2006

### Requirement: Four indicators, each with reference values and a WHO band

The assessment SHALL cover weight-for-age, length/height-for-age, weight-for-length/height,
and BMI-for-age. Each indicator result SHALL carry the measurement used, its unit, the
z-score (two decimals), the percentile (one decimal), the reference −2 SD, median, and +2 SD
values for that sex and age, a band from the set well-below / below / expected / above /
well-above using the WHO cut-offs (−3, −2, +2, +3 SD), and WHO's classification label
where WHO publishes one for that indicator and side (none for weight-for-age above the
range, none for length/height-for-age above the range).

#### Scenario: Below −2 SD is banded and labelled

- **WHEN** a child's length-for-age z-score is −2.4
- **THEN** the indicator's band is below and its WHO label is "stunted"

#### Scenario: Above +2 SD weight-for-age has no WHO label

- **WHEN** a child's weight-for-age z-score is +2.3
- **THEN** the band is above and the WHO label is empty, because WHO directs overweight
  assessment to weight-for-length/height or BMI-for-age

#### Scenario: Reference values accompany each indicator

- **WHEN** an indicator is computed
- **THEN** its result includes the −2 SD, median, and +2 SD values in the measurement's
  unit for the child's sex and age

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

### Requirement: Inputs are validated before any lookup

The assessment SHALL reject, before any computation, an age outside 0–60 months, a
non-positive weight, a height above the sanity limit used by the other tools, or a sex
outside the controlled vocabulary (hard rules 1, 2, 7).

#### Scenario: Off-vocabulary sex rejected

- **WHEN** growth is assessed with a sex value not in the vocabulary
- **THEN** the call is rejected as invalid and no lookup occurs

#### Scenario: Age in months only

- **WHEN** growth is assessed for a child aged 61 months
- **THEN** the call is rejected as invalid

### Requirement: The reference table is validated whole and carries its provenance

The WHO reference table the system reads SHALL be a committed file that records its
source, source URL, retrieval date, and a checksum of each WHO file it was built from, and
SHALL be validated in full when loaded: a missing or malformed parameter for any
indicator, sex, or row SHALL fail the load with a message naming it, and no partial table
SHALL be used. The table SHALL be regenerable from WHO's published files by a re-runnable
script.

#### Scenario: Malformed row fails the load

- **WHEN** the reference table is missing the S parameter for one row
- **THEN** loading fails with a message naming the indicator, sex, and row
- **AND** no assessment can be produced from the partial table

#### Scenario: Provenance recorded

- **WHEN** the reference table is inspected
- **THEN** it names the WHO Child Growth Standards, the URL it was retrieved from, the
  retrieval date, and a checksum per source file

### Requirement: Age granularity is stated

Because the child's age arrives in completed months, the system SHALL use WHO's monthly
reference rows and SHALL state in the result that the comparison is by completed month,
and that under 24 months the height field is read as recumbent length and from 24 months
as standing height.

#### Scenario: Granularity note present

- **WHEN** any growth assessment is returned
- **THEN** its note states that the comparison uses the child's completed month and how
  the height field was interpreted
