## MODIFIED Requirements

### Requirement: Every food entry carries nutrient values and provenance

The system SHALL record, for every food in the table, at minimum: a stable identifier, a
display name, a serving size and unit, calories, protein (grams), and iron (milligrams)
for that serving, and the source the figures were drawn from.

The system SHALL additionally be able to record, for that same serving, these optional
micronutrients: zinc (milligrams), calcium (milligrams), vitamin A (micrograms), iodine
(micrograms), vitamin B12 (micrograms), folate (micrograms), vitamin C (milligrams), and
fiber (grams). An optional micronutrient SHALL be either a non-negative number or absent,
and absent SHALL mean "not measured" — distinct from a recorded zero. Absence SHALL NOT
prevent a food from loading, being looked up, or being used in a meal plan.

#### Scenario: Food entry has required nutrients

- **WHEN** a food is looked up by its identifier
- **THEN** the returned record includes calories, protein, and iron for its serving size
- **AND** the record names the source the values came from

#### Scenario: A recorded micronutrient is returned

- **WHEN** a food carrying a zinc and a vitamin C value is looked up
- **THEN** the returned record reports both values for its serving size

#### Scenario: An unmeasured micronutrient is reported as not measured

- **WHEN** a food with no iodine value recorded is looked up
- **THEN** the returned record reports iodine as not measured rather than as zero

#### Scenario: A measured zero is kept distinct from not measured

- **WHEN** a food records a vitamin C value of zero
- **THEN** the returned record reports zero, not "not measured"

#### Scenario: A negative micronutrient is refused

- **WHEN** a food entry gives a negative folate value
- **THEN** the table fails validation naming the entry and the field

#### Scenario: Entries without micronutrients keep loading

- **WHEN** a table whose entries carry only the required nutrients is loaded
- **THEN** it validates and every entry is available for lookup
