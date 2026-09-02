## MODIFIED Requirements

### Requirement: The table is validated at load time

The system SHALL reject the food table at load time if any entry is missing a required
field, uses an allergen value outside the controlled vocabulary, or specifies an age
outside 0–60 months, rather than admitting a partially-valid table. The same whole-table
validation SHALL run on every administrative write, and a solid food SHALL have a minimum age
of at least 6 months while only the two milk feeds may be under it. The table SHALL be stored
in the application database as whole-table revisions, the first seeded from the committed
file, and the version the system serves SHALL name the revision it came from; the committed
file SHALL remain the fallback when no database table has been loaded.

#### Scenario: Invalid entry blocks loading

- **WHEN** the food table contains an entry with a negative calorie value or an
  unrecognized allergen name
- **THEN** loading the table fails with an error naming the offending entry
- **AND** no partial table is made available to callers

#### Scenario: Invalid entry blocks a write

- **WHEN** an administrative write would put an entry with a negative calorie value into the
  table
- **THEN** the write fails naming the offending entry and the served table is unchanged

#### Scenario: Version names the revision

- **WHEN** the table is served from database revision 3
- **THEN** every result that reports a table version reports `db-3`

### Requirement: Lookup is by stable identifier

The system SHALL support retrieving a single food by a stable identifier and SHALL
report when the identifier is not found, rather than returning a default or empty result.

The system SHALL additionally resolve a plain-language lookup string to a food
deterministically, without language-model involvement: an exact identifier match first,
then a normalized match against the food's identifier or display name, then a
whole-word match (tolerant of plural forms and punctuation) that succeeds only when it
identifies exactly one food. Before matching, the system SHALL ignore words that describe
an amount (numbers, units such as g and ml, measure words such as pieces or servings) or
that frame a question (such as "what", "how much", "nutritional values"); such words SHALL
never choose between foods, and words that describe a preparation (cooked, mashed, raw,
whole) SHALL keep discriminating. A string that matches several foods or no food SHALL be
refused — never silently substituted with a lookalike — and the refusal SHALL name the
closest matching foods, when any exist, so the failure can be corrected in one turn.
Exact-identifier lookup SHALL remain available unchanged for callers that hold real
identifiers. Name resolution SHALL consider only active entries; retrieval by identifier
SHALL return an inactive entry too, so a stored feed can always be priced.

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

#### Scenario: Quantity words are ignored

- **WHEN** a resolution is performed for "nutritional values for 20 grams of sweet
  potatoes" and the table's only sweet-potato entry is `sweet_potato_mashed`
- **THEN** the system returns the `sweet_potato_mashed` entry

#### Scenario: Amount without a food is refused

- **WHEN** a resolution is performed for "20 grams"
- **THEN** the system reports the food is not found, preserving the string as given

#### Scenario: An inactive entry is not resolved by name but is retrievable by identifier

- **WHEN** the only banana entry has been deactivated
- **THEN** a resolution for "bananas" reports the food is not found
- **AND** retrieval by the identifier `banana_mashed` still returns the entry
