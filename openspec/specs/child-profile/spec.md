# child-profile Specification

## Purpose

A child's nutrition profile — age in months, weight, sex, diet preference, allergies, and
an optional doctor's note — owned by a user account. This capability is the input contract
for every nutrient target and meal plan the system produces, so it fixes the
representations that keep those downstream calculations safe and auditable.

## Requirements

### Requirement: Age is represented in months

The system SHALL store and reason about a child's age exclusively as a whole number of
months. The system SHALL NOT persist age in years in any form.

#### Scenario: Age accepted in months

- **WHEN** a profile is created for a child aged 8 months
- **THEN** the stored age is the integer `8`

#### Scenario: Newborn boundary accepted

- **WHEN** a profile is created with an age of `0` months
- **THEN** the profile is accepted

#### Scenario: Negative age rejected

- **WHEN** a profile is created with an age below `0` months
- **THEN** the system rejects the profile as invalid

#### Scenario: Age beyond the supported range rejected

- **WHEN** a profile is created with an age above `60` months
- **THEN** the system rejects the profile as outside the supported range of newborn through ~4 years

#### Scenario: Fractional age rejected

- **WHEN** a profile is created with a non-integer age such as `8.5` months
- **THEN** the system rejects the value rather than rounding it

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

A profile MAY carry a doctor's note. When a note is present and its guidance conflicts
with a general nutrient target, the system SHALL treat the note as authoritative and
SHALL surface the conflict rather than silently blending the two values.

#### Scenario: Profile valid without a note

- **WHEN** a profile is created with no doctor's note
- **THEN** the profile is valid and reports no note

#### Scenario: Note recorded with provenance

- **WHEN** a doctor's note is attached to a profile
- **THEN** the note text and the time it was recorded are both retrievable

#### Scenario: Note overrides a conflicting target

- **WHEN** a doctor's note specifies a nutrient limit that conflicts with the general target for the child's age and weight
- **THEN** the value derived from the note is the one applied
- **AND** the conflict is reported alongside the result rather than hidden

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
and doctor's note.

#### Scenario: Input snapshot reconstructable

- **WHEN** a recommendation is produced from a profile
- **THEN** the age in months, weight, sex, diet preference, allergy set, and doctor's note used are all recoverable for that recommendation

### Requirement: Profiles are reachable only through the owning account

The system SHALL expose a child profile to list, read, replace, and delete only to the
account that owns it, and SHALL apply the same restriction to every read derived from a
profile, including the child's daily nutrient targets. A profile SHALL be created for the
signed-in account and no other. Deleting a profile SHALL remove its allergy associations
and its feeding log.

#### Scenario: Owner lists only their own

- **WHEN** two accounts each own one profile and one of them lists its children
- **THEN** exactly its own profile is returned

#### Scenario: Replace re-dates a changed doctor's note

- **WHEN** the owner replaces a profile with a different doctor's note
- **THEN** the stored note and its recorded-at timestamp both change
- **AND** replacing it with a blank note clears both

#### Scenario: Delete cascades

- **WHEN** the owner deletes a profile that has logged feeds
- **THEN** the profile, its allergies, and its feeds are gone and the list is empty

#### Scenario: A derived targets read is owner-only

- **WHEN** an account requests the daily nutrient targets of a profile it does not own
- **THEN** the request is refused in the same way as a direct read of that profile
- **AND** no target value, diet preference, or age is disclosed

#### Scenario: An unauthenticated targets read is refused

- **WHEN** the daily nutrient targets of any profile are requested without a session
- **THEN** the request is refused

### Requirement: A profile can reproduce the full chat context

A profile SHALL carry, in addition to age in months, weight, sex, diet preference,
allergies, and doctor's note, an optional height in centimetres (required from 36 months)
and an activity level from the controlled vocabulary, so that the stored profile alone is
sufficient to fill every profile-backed tool argument.

#### Scenario: Height required from 36 months

- **WHEN** a profile of 40 months is submitted without a height
- **THEN** the system rejects it with a validation error naming height

#### Scenario: Activity level is a controlled vocabulary

- **WHEN** a profile names an activity level outside the vocabulary
- **THEN** the system rejects it with a validation error

### Requirement: Diet preference selects which nutrient targets are displayed

A profile's diet preference SHALL determine which nutrients appear in the child's displayed
target set and in what order, and SHALL NOT alter any nutrient's reference value. Changing
a profile's diet preference SHALL change the displayed set on the next read, with no other
profile field affected.

#### Scenario: Changing diet changes the displayed set

- **WHEN** the owner changes a profile's diet preference from omnivore to vegan and reads
  the child's targets again
- **THEN** vitamin B12 and an omega-3 DHA advisory are now present
- **AND** the calorie, protein, iron, vitamin D, zinc, and calcium values are unchanged

#### Scenario: Reference values are not diet-specific

- **WHEN** two profiles of identical age, weight, and sex differ only in diet preference
- **THEN** every nutrient present in both displayed sets carries the same reference value,
  reference type, and age band

#### Scenario: The default preference yields the base set

- **WHEN** a profile is created without an explicit diet preference
- **THEN** its displayed set is the base set for the child's age, without the
  vegetarian- or vegan-conditional entries
