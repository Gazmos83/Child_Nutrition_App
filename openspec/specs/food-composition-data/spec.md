# food-composition-data Specification

## Purpose

A curated, versioned lookup table of common infant and toddler foods, each carrying
per-serving nutrient values and safety metadata, that every deterministic nutrient tool
and the infant-safety filter read from — never computed or guessed by the language model.

## Requirements

### Requirement: Every food entry carries nutrient values and provenance

The system SHALL record, for every food in the table, at minimum: a stable identifier, a
display name, a serving size and unit, calories, protein (grams), and iron (milligrams)
for that serving, and the source the figures were drawn from.

#### Scenario: Food entry has required nutrients

- **WHEN** a food is looked up by its identifier
- **THEN** the returned record includes calories, protein, and iron for its serving size
- **AND** the record names the source the values came from

### Requirement: Every food entry carries safety metadata

The system SHALL record, for every food, whether it contains each of the recognized
allergens, whether it is a recognized choking hazard for children under 4, whether it
commonly contains honey, whether it is commonly served unpasteurized, and the minimum
age in months it is appropriate for.

#### Scenario: Safety metadata is present on every entry

- **WHEN** any food is loaded from the table
- **THEN** it reports an allergen set (possibly empty), and boolean flags for choking
  hazard, contains-honey, and commonly-unpasteurized
- **AND** it reports a minimum age in months between 0 and 60

#### Scenario: Known-unsafe foods are flagged correctly

- **WHEN** the table is loaded
- **THEN** every food known to contain honey is flagged `contains_honey`
- **AND** every food on the recognized choking-hazard list (e.g. whole grapes, whole
  nuts, popcorn, hot dogs, hard candy) is flagged `choking_hazard`

### Requirement: The table is validated at load time

The system SHALL reject the food table at load time if any entry is missing a required
field, uses an allergen value outside the controlled vocabulary, or specifies an age
outside 0–60 months, rather than admitting a partially-valid table.

#### Scenario: Invalid entry blocks loading

- **WHEN** the food table contains an entry with a negative calorie value or an
  unrecognized allergen name
- **THEN** loading the table fails with an error naming the offending entry
- **AND** no partial table is made available to callers

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
