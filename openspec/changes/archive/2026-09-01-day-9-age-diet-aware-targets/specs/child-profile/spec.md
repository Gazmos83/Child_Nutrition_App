## MODIFIED Requirements

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

## ADDED Requirements

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
