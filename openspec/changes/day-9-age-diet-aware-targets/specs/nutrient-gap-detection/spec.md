## MODIFIED Requirements

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

## ADDED Requirements

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
