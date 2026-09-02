## MODIFIED Requirements

### Requirement: Doctor's note is optional and takes precedence

A profile MAY carry zero or more note rows. Each row SHALL have a kind from the controlled
vocabulary `doctor` | `preference` (hard rule 2) and one instruction as non-blank text of at
most 500 characters; a profile SHALL carry at most 20 rows and no two identical rows. When a
`doctor` row's guidance conflicts with a general nutrient target, the system SHALL treat the
row as authoritative and SHALL surface the conflict rather than silently blending the two
values. A `preference` row SHALL never change a nutrient target; it MAY only leave foods out
of a plan.

#### Scenario: Profile valid without a note

- **WHEN** a profile is created with no note rows
- **THEN** the profile is valid and reports an empty list of rows

#### Scenario: Note recorded with provenance

- **WHEN** a note row is attached to a profile
- **THEN** the row's kind, text, and the time it was recorded are all retrievable

#### Scenario: Note overrides a conflicting target

- **WHEN** a `doctor` row specifies a nutrient limit that conflicts with the general target
  for the child's age and weight
- **THEN** the value derived from the row is the one applied
- **AND** the conflict is reported alongside the result rather than hidden

#### Scenario: A preference row never changes a target

- **WHEN** a `preference` row states a calorie limit
- **THEN** the general calorie target is used
- **AND** the row is reported as not applied, naming that only a doctor's row can change a
  target

#### Scenario: Rows are validated

- **WHEN** a profile is submitted with a blank row, two identical rows, a row over 500
  characters, or 21 rows
- **THEN** the system rejects it with a validation error

### Requirement: Profiles are reachable only through the owning account

The system SHALL expose a child profile to list, read, replace, and delete only to the
account that owns it, and SHALL apply the same restriction to every read derived from a
profile, including the child's daily nutrient targets. A profile SHALL be created for the
signed-in account and no other. Deleting a profile SHALL remove its allergy associations,
its feeding log, its growth log, and its note rows.

#### Scenario: Owner lists only their own

- **WHEN** two accounts each own one profile and one of them lists its children
- **THEN** exactly its own profile is returned

#### Scenario: Replace re-dates a changed doctor's note

- **WHEN** the owner replaces a profile with a changed or added note row
- **THEN** that row carries a new recorded-at timestamp while an unchanged row keeps its own
- **AND** replacing with an empty list of rows clears every row

#### Scenario: Delete cascades

- **WHEN** the owner deletes a profile that has logged feeds and note rows
- **THEN** the profile, its allergies, its feeds, and its note rows are gone and the list is
  empty

#### Scenario: A derived targets read is owner-only

- **WHEN** an account requests the daily nutrient targets of a profile it does not own
- **THEN** the request is refused in the same way as a direct read of that profile
- **AND** no target value, diet preference, or age is disclosed

#### Scenario: An unauthenticated targets read is refused

- **WHEN** the daily nutrient targets of any profile are requested without a session
- **THEN** the request is refused

### Requirement: Profile inputs are recorded for auditability

The system SHALL retain enough of a profile's state to reconstruct the inputs behind any
recommendation derived from it — age in months, weight, sex, diet preference, allergies,
and the note rows with their kinds.

#### Scenario: Input snapshot reconstructable

- **WHEN** a recommendation is produced from a profile
- **THEN** the age in months, weight, sex, diet preference, allergy set, and note rows (kind
  and text) used are all recoverable for that recommendation

### Requirement: A profile can reproduce the full chat context

A profile SHALL carry, in addition to the date of birth (from which age in months is
derived), weight, sex, diet preference, allergies, and note rows, an optional height in
centimetres (required from 36 months of derived age) and an activity level from the
controlled vocabulary, so that the stored profile alone is sufficient to fill every
profile-backed tool argument, with the age supplied as completed months as of the request.
A stored profile whose derived age has passed 60 months SHALL be refused as out of range
wherever the chat context is built, with a message naming the supported range, rather than
failing the request.

#### Scenario: Height required from 36 months

- **WHEN** a profile with a date of birth 40 months ago is submitted without a height
- **THEN** the system rejects it with a validation error naming height

#### Scenario: Activity level is a controlled vocabulary

- **WHEN** a profile names an activity level outside the vocabulary
- **THEN** the system rejects it with a validation error

#### Scenario: Derived age reaches the tools

- **WHEN** a chat request is made for a profile born eight months ago
- **THEN** every profile-backed tool argument receives `age_months` of `8`

#### Scenario: A child who has aged out is refused, not crashed

- **WHEN** a stored profile's derived age is above 60 months and the owner requests daily
  targets or a chat answer
- **THEN** the response is a validation error naming the supported range

#### Scenario: Note rows reach the tools in order

- **WHEN** a chat request is made for a profile with a doctor row and a preference row
- **THEN** every profile-backed tool argument receives both rows with their kinds, in the
  profile's order
