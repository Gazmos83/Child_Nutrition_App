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

For each of the child's trackable nutrients the report SHALL give the window average, the
target, their ratio, and a flag: `below` when the ratio is under 0.80, `above` when over
1.20, otherwise `adequate`. The trackable set SHALL be whichever nutrients the target
registry declares trackable for that child, and SHALL include calories, protein, iron, and
calcium at minimum. Targets SHALL be the same reference targets the meal planner uses for
the child, including a doctor's-note override where one applies (hard rule 3), and every
target SHALL carry its source and age band.

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

#### Scenario: Calcium is reported alongside the original three

- **WHEN** a report is produced with at least one complete logged day
- **THEN** it carries a flagged entry for calcium as well as for calories, protein, and iron
- **AND** calcium's average is summed from the same per-food values the food table already
  publishes

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

### Requirement: A nutrient the feeding log cannot observe is never flagged

The system SHALL NOT produce an average, ratio, or flag for a nutrient the target registry
declares not trackable for the child, and SHALL NOT report such a nutrient as a deficit.
This holds regardless of whether the nutrient is displayed elsewhere as a reference target.

#### Scenario: Vitamin D is absent from the flagged set

- **WHEN** a gap report is produced for a child with fourteen complete logged days
- **THEN** no flagged entry for vitamin D appears, at any confidence
- **AND** the absence is not reported as missing data or as a deficit

#### Scenario: A vegan child's B12 is not reported as a deficit

- **WHEN** a gap report is produced for a vegan child whose logged feeds contain no
  vitamin B12
- **THEN** no flagged entry for vitamin B12 appears
- **AND** the report does not claim the child's B12 intake is below target, because the log
  cannot distinguish a supplemented child from an unsupplemented one

#### Scenario: A diet edit changes only trackability, never another nutrient's numbers

- **WHEN** a child's profile diet preference is changed and a report is produced again from
  the same logged feeds
- **THEN** the flagged set is exactly the registry's trackable set for the new diet
- **AND** every nutrient present in both reports has an unchanged average and flag
