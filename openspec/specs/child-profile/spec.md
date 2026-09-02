# child-profile Specification

## Purpose

A child's nutrition profile — age in months, weight, sex, diet preference, allergies, and
an optional doctor's note — owned by a user account. This capability is the input contract
for every nutrient target and meal plan the system produces, so it fixes the
representations that keep those downstream calculations safe and auditable.

## Requirements

### Requirement: Age is represented in months

The system SHALL store a child's date of birth and SHALL derive the child's age from it as
a whole number of completed months — as of the current UTC date for the profile, and as of
a given date wherever a dated record needs the age on that day. Every age the system
returns or reasons with SHALL be an integer count of months; the system SHALL NOT persist
or return age in years in any form, and SHALL NOT accept a typed age. A date of birth
later than one day after the current UTC date, or one that puts the child past 60 months,
SHALL be rejected. Completed months SHALL be counted by calendar month, with a birthday
that falls on a day the current month does not have treated as the last day of that month.

#### Scenario: Age accepted in months

- **WHEN** a profile is created with a date of birth eight calendar months before today
- **THEN** the returned age is the integer `8`, derived from the stored date of birth

#### Scenario: Newborn boundary accepted

- **WHEN** a profile is created with today's date as the date of birth
- **THEN** the profile is accepted and its age is `0`

#### Scenario: Negative age rejected

- **WHEN** a profile is created with a date of birth two days after today, which would make
  the age negative
- **THEN** the system rejects the profile as invalid

#### Scenario: Age beyond the supported range rejected

- **WHEN** a profile is created with a date of birth more than `60` months before today
- **THEN** the system rejects the profile as outside the supported range of newborn through
  ~4 years

#### Scenario: Fractional age rejected

- **WHEN** a profile is submitted with a typed age such as `8` or `8.5` months instead of a
  date of birth
- **THEN** the system rejects the request as invalid; age is only ever derived as whole
  completed months

#### Scenario: Month-end birthday counted by calendar month

- **WHEN** a child born on 31 January is assessed on 28 February and on 31 March of a
  non-leap year
- **THEN** the ages are `1` month and `2` months respectively

### Requirement: Allergies are a controlled vocabulary

The system SHALL restrict recorded allergies to a fixed, enumerated set of allergen values
and SHALL NOT accept free text in the allergy field.

#### Scenario: Known allergen accepted

- **WHEN** a profile records an allergy to a value in the allergen vocabulary
- **THEN** the association is persisted

#### Scenario: Free text rejected

- **WHEN** a profile records an allergy value not present in the allergen vocabulary
- **THEN** the system rejects the value
- **AND** no allergy association is persisted

#### Scenario: Multiple allergies recorded independently

- **WHEN** a profile records allergies to three distinct allergens
- **THEN** all three are retrievable as separate values, not as one combined string

#### Scenario: Duplicate allergen not double-recorded

- **WHEN** the same allergen is recorded twice for one profile
- **THEN** the profile carries that allergen exactly once

#### Scenario: No allergies is a valid state

- **WHEN** a profile records no allergies
- **THEN** the profile is valid and reports an empty allergy set

### Requirement: Diet preference is a controlled vocabulary

The system SHALL restrict a profile's diet preference to a fixed, enumerated set of values
and SHALL NOT accept free text.

#### Scenario: Known preference accepted

- **WHEN** a profile sets a diet preference within the vocabulary
- **THEN** the value is persisted

#### Scenario: Free text rejected

- **WHEN** a profile sets a diet preference outside the vocabulary
- **THEN** the system rejects the value

#### Scenario: Unspecified preference has a defined default

- **WHEN** a profile is created without an explicit diet preference
- **THEN** the profile carries the vocabulary's designated default rather than a null or empty value

### Requirement: Weight is a positive measurement in fixed units

The system SHALL store weight as a positive value in a single documented unit
(kilograms), and SHALL reject non-positive or absent values.

#### Scenario: Valid weight accepted

- **WHEN** a profile is created with a weight of `8.4` kg
- **THEN** the value is persisted without loss of the recorded precision

#### Scenario: Non-positive weight rejected

- **WHEN** a profile is created with a weight of `0` or below
- **THEN** the system rejects the profile as invalid

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

### Requirement: Profiles are owned by exactly one account

Every child profile SHALL reference the account that owns it, and the system SHALL reject
a profile that references no account or an account that does not exist.

#### Scenario: Profile bound to its owner

- **WHEN** a profile is created by an authenticated account
- **THEN** the stored profile references that account as owner

#### Scenario: Orphan profile rejected

- **WHEN** a profile is created referencing an account that does not exist
- **THEN** the system rejects the operation

#### Scenario: One account owns several profiles

- **WHEN** an account creates profiles for two children
- **THEN** both profiles are retrievable for that account and are distinguishable from each other

### Requirement: Profile inputs are recorded for auditability

The system SHALL retain enough of a profile's state to reconstruct the inputs behind any
recommendation derived from it — age in months, weight, sex, diet preference, allergies,
and the note rows with their kinds.

#### Scenario: Input snapshot reconstructable

- **WHEN** a recommendation is produced from a profile
- **THEN** the age in months, weight, sex, diet preference, allergy set, and note rows (kind
  and text) used are all recoverable for that recommendation

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

### Requirement: Diet preference selects which nutrient targets are displayed

A profile's diet preference SHALL determine which nutrients appear in the child's displayed
target set and in what order, and SHALL NOT alter any nutrient's reference value. Changing
a profile's diet preference SHALL change the displayed set on the next read, with no other
profile field affected. Zinc SHALL NOT appear in any displayed target set: it is a stored
food-composition value with no reference target for any age or diet.

#### Scenario: Changing diet changes the displayed set

- **WHEN** the owner changes a profile's diet preference from omnivore to vegan and reads
  the child's targets again
- **THEN** vitamin B12 and an omega-3 DHA advisory are now present
- **AND** the calorie, protein, iron, vitamin D, and calcium values are unchanged

#### Scenario: Reference values are not diet-specific

- **WHEN** two profiles of identical age, weight, and sex differ only in diet preference
- **THEN** every nutrient present in both displayed sets carries the same reference value,
  reference type, and age band

#### Scenario: The default preference yields the base set

- **WHEN** a profile is created without an explicit diet preference
- **THEN** its displayed set is the base set for the child's age, without the
  vegetarian- or vegan-conditional entries

#### Scenario: Zinc has no target row

- **WHEN** the owner reads the targets of any profile, whatever its age or diet preference
- **THEN** no zinc row is present in the displayed set

