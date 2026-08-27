## ADDED Requirements

### Requirement: Growth assessments render as a structured card in the direct voice

When a response includes a growth-assessment result the UI SHALL render a card with one
row per indicator showing the measurement, the percentile, a marker on a −3 to +3
standard-deviation track, the WHO reference values (−2 SD, median, +2 SD), and WHO's label
when the result carries one; skipped indicators SHALL appear with their reason. The card
SHALL name the standard and its year and SHALL tell the parent that a single measurement
is a snapshot their pediatrician can plot over time. All copy on the card SHALL be direct:
no wordplay about weight or size, no diagnosis, the next step named.

#### Scenario: Four indicators shown

- **WHEN** a result contains four computed indicators
- **THEN** the card shows four rows, each with a percentile, a marker, and reference values,
  and a source line naming the WHO Child Growth Standards (2006)

#### Scenario: Skipped indicator explained

- **WHEN** a result lists BMI-for-age as skipped because no height was supplied
- **THEN** the card shows a BMI-for-age row with the reason pointing to the side panel
  instead of a percentile

#### Scenario: WHO label shown plainly

- **WHEN** an indicator's band is outside the expected range and carries a WHO label
- **THEN** the row shows the label as WHO's term and the sentence that follows names the
  pediatrician as the next step, with no playful wording
