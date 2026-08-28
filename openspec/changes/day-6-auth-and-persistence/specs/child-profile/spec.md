## ADDED Requirements

### Requirement: Profiles are reachable only through the owning account

The system SHALL expose a child profile to list, read, replace, and delete only to the
account that owns it. A profile SHALL be created for the signed-in account and no other.
Deleting a profile SHALL remove its allergy associations and its feeding log.

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
