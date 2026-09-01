## ADDED Requirements

### Requirement: The side panel shows the child's daily nutrient targets

The UI SHALL show, in the side panel beside the child's details, a persistent Daily-targets
section listing the child's nutrient targets in the order the server returns them, each with
its value, unit, reference type, age band, and source. The section SHALL read the signed-in
account's saved child; when no child is saved yet it SHALL say so instead of showing
numbers. The UI SHALL NOT compute, reorder, or round any target itself, since no nutrient
number a parent sees may originate in the browser.

#### Scenario: Targets appear in server order

- **WHEN** the parent opens the child tab for a saved 9-month-old
- **THEN** the Daily-targets section lists the targets in the order received, without
  client-side sorting
- **AND** each row shows its value with unit, its reference type, and its source

#### Scenario: No child yet

- **WHEN** the account has no saved child and the parent opens the child tab
- **THEN** the Daily-targets section explains that the child's details come first and shows
  no target values

#### Scenario: Unsaved edits do not produce numbers

- **WHEN** the parent edits the child's age in the form without saving
- **THEN** the Daily-targets section does not show targets for the unsaved age, and says
  the details must be saved first

#### Scenario: Targets refresh after a profile change

- **WHEN** the parent saves a change to the child's age or diet preference
- **THEN** the Daily-targets section reflects the saved profile without a page reload

### Requirement: Display-only targets and advisories are visually distinct from tracked ones

A target the system does not compare against logged intake SHALL be rendered with its value
and its parent-facing reason, and SHALL NOT be given a progress indicator or a
below/adequate/above badge. An advisory entry SHALL be rendered as guidance text with its
source and publication date, and SHALL NOT be given a value or a progress indicator.

#### Scenario: Vitamin D shows a reason and no progress bar

- **WHEN** the Daily-targets section renders vitamin D
- **THEN** it shows the target value and a reason explaining that intake comes from
  supplements and sunlight rather than logged food
- **AND** it renders no progress indicator and no flag badge

#### Scenario: A vegan child's B12 and DHA read as guidance

- **WHEN** the Daily-targets section renders for a vegan child
- **THEN** vitamin B12 shows its value with supplement guidance and no progress indicator
- **AND** the omega-3 DHA entry shows guidance text with its source and publication date,
  and no value

#### Scenario: A tracked target keeps its progress indicator

- **WHEN** the Daily-targets section renders calcium for a child with complete logged days
- **THEN** calcium shows its progress against target and its flag
- **AND** exactly one progress track is drawn for that row

### Requirement: The panel says when a doctor's note is on file but not applied to it

Because the Daily-targets section reports general reference targets rather than
note-adjusted ones, the UI SHALL state when a doctor's note is on file for the child and
that the note is applied when meal plans are generated, so a parent is never left to infer
that the note was ignored (hard rule 3).

#### Scenario: A note on file is disclosed

- **WHEN** the child's profile carries a doctor's note and the parent opens the child tab
- **THEN** the Daily-targets section states that a note is on file and that it is applied
  when planning meals

#### Scenario: No note, no claim

- **WHEN** the child's profile carries no doctor's note
- **THEN** the Daily-targets section makes no statement about a note
