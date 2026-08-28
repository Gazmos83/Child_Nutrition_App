# nutrient-gap-detection Specification

## Purpose

Compares a child's logged intake to their daily targets over a rolling window that widens
as more complete days are logged, producing deterministic, confidence-labelled gap flags
for calories, protein, and iron without any learned model.

## Requirements

### Requirement: Detection is deterministic and lookup-driven

The system SHALL compute gap reports from logged entries, the food-composition table, and
the child's reference targets by arithmetic alone. The language model SHALL NOT compute,
estimate, or adjust any figure in a gap report. The same inputs SHALL always produce the
same report.

#### Scenario: Repeated detection is identical

- **WHEN** gap detection runs twice on the same entries, child, and reference day
- **THEN** the two reports are identical

### Requirement: Windows widen with complete days logged

The system SHALL count *complete* days — local calendar days with at least one entry and
no unquantified entry — within the last fourteen days before the reference day, excluding
the reference day itself, and SHALL apply:

- 0 complete days → status `insufficient_data`, no flags;
- 1–2 complete days → confidence `low`, window equal to the days available, flags are
  directional only;
- 3–6 complete days → confidence `medium`, three-day window;
- 7 or more complete days → confidence `high`, seven-day window.

The report SHALL state the number of complete days, the window used, the number of
incomplete days excluded, and the reference day.

#### Scenario: No complete days

- **WHEN** every logged day contains an unquantified breast-milk entry
- **THEN** the report's status is `insufficient_data`, it lists the incomplete-day count,
  and no nutrient is flagged

#### Scenario: Two days → low confidence

- **WHEN** exactly two complete days are logged
- **THEN** confidence is `low`, the window is two days, and flags are marked directional

#### Scenario: Four days → medium, three-day window

- **WHEN** four complete days are logged
- **THEN** confidence is `medium` and averages use the three most recent complete days

#### Scenario: Nine days → high, seven-day window

- **WHEN** nine complete days are logged
- **THEN** confidence is `high` and averages use the seven most recent complete days

#### Scenario: Reference day excluded

- **WHEN** the reference day has entries
- **THEN** those entries do not enter the window, because the day is not yet complete

### Requirement: Flags compare window averages to the child's targets

For each of calories, protein, and iron the report SHALL give the window average, the
target, their ratio, and a flag: `below` when the ratio is under 0.80, `above` when over
1.20, otherwise `adequate`. Targets SHALL be the same reference targets the meal planner
uses for the child, including a doctor's-note override where one applies (hard rule 3),
and every target SHALL carry its source and age band.

#### Scenario: Threshold boundaries

- **WHEN** a nutrient's ratio is 0.79, 0.80, or 1.21
- **THEN** its flag is `below`, `adequate`, and `above` respectively

#### Scenario: Doctor's note prevents a false deficit

- **WHEN** the doctor's note limits calories to 650 kcal, the general target is 750 kcal,
  and the window average is 640 kcal
- **THEN** calories are `adequate` against 650 kcal and the report shows the override
  conflict

#### Scenario: Targets cite their source

- **WHEN** any report is produced with flags
- **THEN** each target names its source and age band

### Requirement: Every gap detection is logged for audit

The system SHALL emit an audit record for every gap detection containing the child input
snapshot, the number of complete and incomplete days, the window, the confidence, each
nutrient's average, target, ratio, flag, and target source, and the override outcome. When
the detection runs inside a request, the record SHALL carry that request's correlation
identifier, the account identifier, and the stored child profile identifier the inputs
came from.

#### Scenario: Audit record present

- **WHEN** gap detection runs, including the `insufficient_data` outcome
- **THEN** an audit record with those fields is emitted

#### Scenario: Audit record is correlated

- **WHEN** gap detection runs for a signed-in parent's saved child through the chat
- **THEN** the audit record carries the request id, the account id, and the child profile id
