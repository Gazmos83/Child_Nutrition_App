## Purpose

Keeps a dated record of a child's weight and length/height measurements so growth can be
followed over time, placing every measurement on the WHO Child Growth Standards for the
child's age on that day, and keeping the profile's current weight and height in step with
the newest measurement.

## ADDED Requirements

### Requirement: A growth measurement is a dated, validated record stored raw

A growth measurement SHALL consist of the calendar date it was taken, a positive weight in
kilograms, and an optional positive length/height in centimetres, and SHALL be stored
against exactly one child profile with nothing derived from it (no age, no z-score, no
percentile). The system SHALL reject a measurement dated before the child's date of birth,
dated more than one day after the current UTC date, or dated when the child is older than
60 months, and SHALL reject a second measurement for the same child on the same date.

#### Scenario: Weight-only measurement accepted

- **WHEN** the owner posts a measurement dated today with a weight of `7.2` kg and no
  length/height
- **THEN** the response is 201 with the stored measurement, its identifier, and a null
  length/height

#### Scenario: Measurement before birth rejected

- **WHEN** a measurement is dated the day before the child's date of birth
- **THEN** the response is 422 and the message names the date of birth

#### Scenario: Measurement in the future rejected

- **WHEN** a measurement is dated two days after today
- **THEN** the response is 422 and no row is stored

#### Scenario: Same day twice rejected

- **WHEN** a second measurement is posted for the same child and the same date
- **THEN** the response is 409 and the first measurement is unchanged

#### Scenario: Non-positive weight rejected

- **WHEN** a measurement is posted with a weight of `0`
- **THEN** the response is 422

### Requirement: Each measurement is read back with its age and WHO assessment computed by arithmetic

On every read the system SHALL return each measurement with the child's age in completed
months on the measurement date, derived from the stored date of birth, and with the growth
assessment for that age, sex, weight, and length/height as the growth-assessment capability
defines it (indicators, skipped indicators, reference values, WHO source and year). These
values SHALL be computed on read, never stored, and SHALL come from table arithmetic, not
from the language model. The list SHALL be ordered newest measurement first.

#### Scenario: Age at the measurement, not today

- **WHEN** a child born on 2026-01-10 has measurements dated 2026-05-09 and 2026-05-10
- **THEN** the list reports 3 months for the first and 4 months for the second, whatever
  today's date is

#### Scenario: Four indicators with height, one without

- **WHEN** one measurement carries a length/height and another does not
- **THEN** the first is returned with four computed indicators and the second with
  weight-for-age computed and three indicators skipped, and both reads succeed

#### Scenario: Median weight reads as the 50th percentile

- **WHEN** a measurement's weight equals the WHO median weight-for-age for the child's sex
  and age on that date
- **THEN** its weight-for-age percentile is 50.0

#### Scenario: Newest first

- **WHEN** three measurements are stored on different dates
- **THEN** the list returns them in descending date order

### Requirement: The newest measurement sets the profile's weight and height

When a posted measurement is dated on or after every measurement already stored for the
child, the system SHALL set the profile's weight to the measurement's weight and, when the
measurement carries a length/height, the profile's height to it, in the same transaction
as the insert. A measurement dated earlier than an existing one SHALL NOT change the
profile. A newest measurement without a length/height SHALL leave the profile's height as
it was. Editing the profile SHALL NOT create a measurement, and deleting a measurement
SHALL NOT change the profile.

#### Scenario: Today's measurement updates the profile

- **WHEN** the owner posts a measurement dated today with weight `7.2` kg and height
  `66.0` cm for a profile showing `6.0` kg and `60.0` cm
- **THEN** reading the profile shows `7.2` kg and `66.0` cm

#### Scenario: Back-dated measurement leaves the profile alone

- **WHEN** the owner then posts a measurement dated a month earlier with weight `6.5` kg
- **THEN** the profile still shows `7.2` kg and `66.0` cm

#### Scenario: Newest without height keeps the height

- **WHEN** the newest measurement carries a weight and no length/height
- **THEN** the profile takes the new weight and keeps its previous height

#### Scenario: Profile edits do not log measurements

- **WHEN** the owner changes the profile's weight through the profile form
- **THEN** the measurement list is unchanged

### Requirement: The growth log is reachable only by the owning account

The system SHALL expose listing, adding, and deleting measurements only to the account that
owns the child (see `user-account`); another account SHALL receive the same 404 a
nonexistent child would produce, an unauthenticated caller SHALL be refused, and deleting a
child SHALL remove its measurements.

#### Scenario: Owner removes one measurement

- **WHEN** the owner deletes one of two stored measurements
- **THEN** the response is 204 and the list contains only the other

#### Scenario: Another account is refused like absence

- **WHEN** a different account lists, posts to, or deletes from the child's growth log
- **THEN** each response is the same 404 a nonexistent child would produce

#### Scenario: Deleting the child removes the log

- **WHEN** the owner deletes the child profile
- **THEN** no measurement for that child remains
