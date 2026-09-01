# food-composition-data — delta for food-name-resolution

## MODIFIED Requirements

### Requirement: Lookup is by stable identifier

The system SHALL support retrieving a single food by a stable identifier and SHALL
report when the identifier is not found, rather than returning a default or empty result.

The system SHALL additionally resolve a plain-language lookup string to a food
deterministically, without language-model involvement: an exact identifier match first,
then a normalized match against the food's identifier or display name, then a
whole-word match (tolerant of plural forms and punctuation) that succeeds only when it
identifies exactly one food. A string that matches several foods or no food SHALL be
refused — never silently substituted with a lookalike — and the refusal SHALL name the
closest matching foods, when any exist, so the failure can be corrected in one turn.
Exact-identifier lookup SHALL remain available unchanged for callers that hold real
identifiers.

#### Scenario: Unknown food identifier

- **WHEN** a lookup is performed for an identifier not present in the table
- **THEN** the system reports the food is not found
- **AND** does not silently substitute a similar food

#### Scenario: Common name resolves to its entry

- **WHEN** a resolution is performed for "bananas" and the table's only banana entry is
  "Banana, mashed" (`banana_mashed`)
- **THEN** the system returns the `banana_mashed` entry

#### Scenario: Slugified display name resolves

- **WHEN** a resolution is performed for `sweet_potato_cooked_mashed` and the table
  holds `sweet_potato_mashed` ("Sweet potato, cooked and mashed")
- **THEN** the system returns the `sweet_potato_mashed` entry

#### Scenario: Ambiguous name is refused with candidates

- **WHEN** a resolution is performed for "apple" and the table holds both a cooked-apple
  and a raw-apple-chunks entry
- **THEN** the system reports the food is not found
- **AND** the report names both candidate entries
- **AND** neither is silently chosen

#### Scenario: Unrecognized name is refused with closest matches

- **WHEN** a resolution is performed for a string matching no entry
- **THEN** the system reports the food is not found, preserving the string as given
- **AND** the report includes the closest-matching entries when any are close
