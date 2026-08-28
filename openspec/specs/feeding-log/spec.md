# feeding-log Specification

## Purpose

Records what a child was actually fed — as opposed to what was planned — as validated,
controlled-vocabulary entries whose nutrient content is derived from the curated food
table, and answers "what has the child had today and what is still needed".

## Requirements

### Requirement: A feeding entry is a validated, controlled-vocabulary record

A feeding entry SHALL consist of a time-zone-aware timestamp, a feeding type from the
closed vocabulary `breastmilk`, `formula`, `solid`, `water` (hard rule 2), an optional
food identifier from the food-composition table, an optional quantity, and a unit of `ml`
or `g`. The system SHALL reject an entry with a free-text feeding type, a food identifier
not in the table, a non-positive quantity, or a unit that does not match the food's
serving unit.

#### Scenario: Solid entry requires a known food

- **WHEN** a `solid` entry is submitted without a food identifier, or with one not in the
  table
- **THEN** the entry is rejected with a validation error naming the problem

#### Scenario: Unit must match the food

- **WHEN** a `formula` entry is submitted in grams
- **THEN** the entry is rejected, because formula is measured in millilitres in the table

#### Scenario: Off-vocabulary feeding type rejected

- **WHEN** an entry names a feeding type outside the four allowed values
- **THEN** the entry is rejected with a validation error

### Requirement: Quantity is required except for breast milk

The system SHALL require a positive quantity for `formula`, `solid`, and `water` entries
and SHALL accept a `breastmilk` entry without a quantity. An unquantified entry SHALL
contribute no nutrients and SHALL mark its day as incomplete for any window-based analysis.

#### Scenario: Unquantified breast milk accepted

- **WHEN** a `breastmilk` entry is submitted with no quantity
- **THEN** the entry is accepted, its nutrient contribution is zero, and the day is marked
  incomplete

#### Scenario: Unquantified formula rejected

- **WHEN** a `formula` entry is submitted with no quantity
- **THEN** the entry is rejected with a validation error

### Requirement: Nutrient content is derived from the food table by arithmetic

The system SHALL compute an entry's calories, protein, fat, carbohydrate, iron, and calcium
as `quantity ÷ serving size × per-serving value` from the food-composition table. The
language model SHALL NOT compute or estimate any of these. Breast milk and formula SHALL
map to the table's milk-feed entries by default, with formula overridable to another
milk-feed identifier. Water SHALL contribute zero nutrients.

#### Scenario: Formula volume converted

- **WHEN** 150 ml of iron-fortified formula (table: 67 kcal, 1.4 g protein, 1.2 mg iron
  per 100 ml) is logged
- **THEN** the entry's nutrients are 100.5 kcal, 2.1 g protein, and 1.8 mg iron

#### Scenario: Client-supplied nutrients are ignored

- **WHEN** a request carries entries with nutrient figures attached
- **THEN** the system recomputes every figure from the table and uses only its own values

### Requirement: Logging is optional and never gates a plan

The system SHALL produce meal plans, targets, and answers for a child with no feeding
entries exactly as it does today. No capability SHALL require a non-empty log.

#### Scenario: Empty log, unchanged plan

- **WHEN** a meal plan is requested for a child with no feeding entries
- **THEN** the plan is identical to the plan produced before the feeding log existed

### Requirement: Daily totals and remaining targets are available for a day

The system SHALL report, for a given calendar day in the parent's time zone, the summed
nutrients of that day's entries, and SHALL report the child's daily targets minus that
intake, floored at zero, using the same targets the meal planner uses (including any
doctor's-note override, flagged not blended — hard rule 3).

#### Scenario: Daily totals

- **WHEN** three entries are logged on the same local day
- **THEN** the day's totals equal the sum of the three entries' nutrients and entries from
  other days are not included

#### Scenario: Remaining targets honour the doctor's note

- **WHEN** the doctor's note limits calories to 650 kcal, the general target is 750 kcal,
  and 300 kcal has been logged today
- **THEN** remaining calories are 350 kcal and the response flags that the note's value
  was used

#### Scenario: Remaining cannot go negative

- **WHEN** logged intake exceeds a target
- **THEN** the remaining value for that nutrient is reported as zero

### Requirement: Foods are listable for the picker

The system SHALL expose the food-composition table's identifiers, names, categories,
serving sizes, serving units, and minimum ages, without user data, so a form can offer
only foods the table knows.

#### Scenario: Every table entry listed

- **WHEN** the food list is requested
- **THEN** every food in the table appears once with its identifier, name, category,
  serving size, serving unit, and minimum age in months

### Requirement: The log is stored per child and read by its owner

The system SHALL store each logged feed against a child profile — the time it happened,
the feeding type, the food identifier when any, the quantity, and the unit — and nothing
derived from the food table. It SHALL expose the log only to the account that owns the
child (see `user-account`), SHALL price every entry from the committed food table on each
read, SHALL bound a read to a requested number of days (default fourteen, at most ninety)
and two hundred entries newest first, and SHALL skip, with a logged warning, a stored entry
whose food the table no longer knows rather than failing the read.

#### Scenario: Logged, stored, read back priced

- **WHEN** the owner posts a valid 150 ml formula feed for their child
- **THEN** the response is 201 with the entry, its identifier, and 100.5 kcal
- **AND** listing the child's feeds returns that entry with the same nutrients

#### Scenario: Re-posting the same entry is idempotent

- **WHEN** an entry with an identifier already stored for the same child is posted again
- **THEN** the response is 201 with the stored entry and no second row exists

#### Scenario: Table contradictions still rejected

- **WHEN** a `solid` entry names a food not in the table, or a unit the food is not measured
  in
- **THEN** the response is 422 and the message names the food or the unit

#### Scenario: Owner removes one entry

- **WHEN** the owner deletes one of two logged feeds
- **THEN** the response is 204 and the list contains only the other

#### Scenario: Another account is refused like absence

- **WHEN** a different account lists, posts to, or deletes from the child's log
- **THEN** each response is the same 404 a nonexistent child would produce

### Requirement: A feed the assistant logs reaches the account's log

When the assistant's `log_feeding` tool runs during a chat turn, the tool result SHALL
carry the priced entry with its identifier, and the browser SHALL post that entry to the
child's feeding log so it is stored; the chat service itself SHALL NOT write to the
database.

#### Scenario: Model-logged feed is persisted

- **WHEN** a chat turn's `tool` event reports a successful `log_feeding`
- **THEN** the browser posts the entry to the child's feeding log and the log shows it
