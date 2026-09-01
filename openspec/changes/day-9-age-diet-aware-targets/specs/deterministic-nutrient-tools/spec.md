## ADDED Requirements

### Requirement: Every reference intake figure comes from one declarative registry

The system SHALL hold every dietary reference intake figure it uses — the per-age-band
value, its reference type (adequate intake, recommended dietary allowance, or estimated
energy requirement), its unit, its tolerable upper intake level where one is published,
and its source citation — in a single declarative registry. No reference figure SHALL be
defined in more than one place, and adding a nutrient to the registry SHALL be sufficient
to give it a target. Registry figures SHALL match the values cited in the knowledge base
for the same nutrient and age band (hard rule 5 provenance).

#### Scenario: A figure is defined exactly once

- **WHEN** the reference value for a nutrient and age band is requested twice through
  different callers
- **THEN** both callers receive the same value, reference type, band label, and source

#### Scenario: Registry figures agree with the knowledge base

- **WHEN** any registry value is compared with the corresponding published value in the
  nutrition knowledge base for the same nutrient and age band
- **THEN** the two agree

#### Scenario: Every target names its provenance

- **WHEN** a target is produced for any nutrient in the registry
- **THEN** it carries its unit, reference type, age-band label, and source
- **AND** it carries its tolerable upper intake level when one is published for that band

### Requirement: Daily targets are an ordered set selected by age and diet preference

The system SHALL produce a child's daily targets as an ordered set whose membership and
order are determined by the child's age in months and diet preference. Selection and
ordering SHALL be deterministic and SHALL involve no language-model call. Diet preference
SHALL affect only which nutrients are present and their order; it SHALL NOT change any
nutrient's reference value, because reference intakes are not diet-specific.

#### Scenario: Order responds to age

- **WHEN** targets are produced for a 9-month-old and for a 30-month-old on the same diet
- **THEN** both sets are ordered by the child's age-appropriate priority
- **AND** iron precedes protein for the 9-month-old, reflecting the sharp rise in iron
  need from 7 months

#### Scenario: Membership responds to diet preference

- **WHEN** targets are produced for a vegan child and for an omnivorous child of the same
  age and weight
- **THEN** the vegan child's set additionally contains vitamin B12
- **AND** every nutrient present in both sets carries an identical reference value

#### Scenario: Selection is deterministic

- **WHEN** targets are produced twice for the same age, weight, sex, and diet preference
- **THEN** the two sets are identical in membership, order, and values

#### Scenario: An advisory nutrient carries guidance instead of a number

- **WHEN** targets are produced for a vegan child
- **THEN** the set contains an omega-3 DHA entry that carries guidance text, a source, and
  a publication date, and carries no numeric target
- **AND** that entry is never compared against logged intake

### Requirement: Each target declares whether logged intake is compared against it

Each target SHALL declare whether the feeding log can observe intake for that nutrient.
A nutrient SHALL be declared trackable only when the food-composition table supplies a
per-food value for it and the child's diet permits a food in the table that provides it.
A target that is not trackable SHALL carry a parent-facing reason and SHALL NOT be given
an average, a ratio, or a flag anywhere in the system.

#### Scenario: Vitamin D is displayed but never scored

- **WHEN** targets are produced for a child of any age
- **THEN** vitamin D carries a numeric target, its reference type, and its source
- **AND** it is marked not trackable, with a reason stating that intake comes from
  supplements and sunlight rather than logged food
- **AND** it carries no average, ratio, or flag

#### Scenario: Vitamin B12 carries diet-appropriate guidance and no score yet

- **WHEN** targets are produced for a vegetarian child and for a vegan child
- **THEN** both entries show vitamin B12 as not trackable, because the food-composition
  table does not yet supply a per-food B12 value
- **AND** the vegan child's entry carries guidance that every vegan child needs a B12
  supplement or reliably fortified foods
- **AND** the vegetarian child's entry notes that dairy and eggs usually cover B12

#### Scenario: A non-trackable target cannot carry a flag

- **WHEN** any target marked not trackable is produced
- **THEN** the system rejects it as invalid if an average, ratio, or flag is attached
