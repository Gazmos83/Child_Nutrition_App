## Purpose

Keeps a dated record of a child's weight and length/height measurements so growth can be
followed over time, placing every measurement on the WHO Child Growth Standards for the
child's age on that day, and keeping the profile's current weight and height in step with
the newest measurement.

## ADDED Requirements

### Requirement: Percentile reference curves are available for the child's sex, computed by arithmetic

For a child, the system SHALL provide, for each of the four indicators, the WHO reference
values at the 10th, 20th, 30th, 40th, 50th, 60th, 70th, 80th, and 90th percentiles for the
child's sex: at every completed month from 0 to 60 for weight-for-age, length/height-for-age,
and BMI-for-age, and at every whole centimetre of the table the child's current age uses
(length under 24 months, height from 24 months) for weight-for-length/height, naming which
table it is. Every value SHALL be derived from the published LMS parameters by the inverse
of the z-score arithmetic the assessment uses — no value from the language model — and the
response SHALL name the standard and its year. The read SHALL be exposed only to the
account that owns the child.

#### Scenario: Nine curves per indicator, the 50th equal to the median

- **WHEN** the owner reads the curves for a girl aged 8 months
- **THEN** each of the four indicators carries nine curves at the 10th through 90th
  percentiles, and every 50th-percentile value equals the WHO median for that sex and
  x-value to one decimal

#### Scenario: Percentiles are ordered

- **WHEN** any indicator's curves are read
- **THEN** at every x-value the 10th-percentile value is below the 20th, and so on up to
  the 90th

#### Scenario: Weight-for-length under 24 months, weight-for-height from 24

- **WHEN** the curves are read for a child under 24 months and for a child of 30 months
- **THEN** the first weight-for-length/height set spans the length table (45–110 cm) and
  says so, and the second spans the height table (65–120 cm) and says so

#### Scenario: Another account is refused like absence

- **WHEN** a different account reads the child's curves
- **THEN** the response is the same 404 a nonexistent child would produce

### Requirement: Each measurement carries its exact age in months for plotting

Alongside the completed months used for the assessment, each measurement read back SHALL
carry the age on the measurement day in months to two decimals (days since birth divided by
the mean month length), so measurements within the same completed month can be placed
along an age axis. The assessment SHALL continue to use completed months.

#### Scenario: Two measurements in one completed month

- **WHEN** a child born on 2026-01-10 has measurements on 2026-05-12 and 2026-05-25
- **THEN** both report `4` completed months and exact ages that differ by about 0.43
  months, the second larger
