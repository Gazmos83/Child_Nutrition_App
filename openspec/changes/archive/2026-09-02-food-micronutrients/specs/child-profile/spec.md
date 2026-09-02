## MODIFIED Requirements

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
