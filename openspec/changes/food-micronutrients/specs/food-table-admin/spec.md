## MODIFIED Requirements

### Requirement: Foods are created and edited with complete safety metadata and a source

An administrator SHALL be able to create a food and replace an existing food's entry by its
identifier. Every write SHALL require the four safety fields — choking hazard, contains
honey, commonly unpasteurized, minimum age in months — explicitly, with no default, and a
non-empty source. A solid food SHALL have a minimum age of at least 6 months; the
`milk_feed` category SHALL be reserved for the two protected milk feeds (breast milk and
iron-fortified formula), whose category cannot change. An identifier SHALL be immutable; a
create with an existing identifier SHALL be refused. Every write SHALL validate the whole
resulting table exactly as the committed file is validated, and a failing write SHALL change
nothing.

The edit form SHALL offer, in a group separated from the required nutrients and labelled as
optional, an entry field with its unit for each optional micronutrient the table records:
zinc, vitamin A, iodine, vitamin B12, folate, vitamin C, and fiber. Calcium SHALL stay
among the fields the form already offers. A micronutrient field left blank SHALL be written
as "not measured"; a field given `0` SHALL be written as a measured zero. A micronutrient
field given anything other than a blank or a non-negative number SHALL be refused with a
message naming the field, and nothing SHALL be written. Editing an existing food SHALL
show each recorded micronutrient at its stored value and each unmeasured one as blank.

#### Scenario: Create with every field

- **WHEN** an administrator posts a new solid with nutrients, category, allergens from the
  vocabulary, the four safety fields, minimum age 6, and a source
- **THEN** the response is 201 and the food appears in the food picker

#### Scenario: Create with micronutrients

- **WHEN** an administrator fills the zinc, vitamin A, and vitamin C fields on a new solid
  and leaves the other micronutrients blank
- **THEN** the response is 201 and reading the food back reports the three values and
  reports the remaining micronutrients as not measured

#### Scenario: Micronutrients are optional

- **WHEN** an administrator saves a food with every micronutrient field left blank
- **THEN** the write succeeds and the food carries no micronutrient values

#### Scenario: A negative micronutrient is refused

- **WHEN** an administrator enters `-1` in the iodine field
- **THEN** the write is refused with a message naming the field and nothing is written

#### Scenario: Editing shows stored micronutrients

- **WHEN** an administrator opens a food that records zinc but not folate
- **THEN** the zinc field shows the stored value and the folate field is blank

#### Scenario: A missing safety answer is refused

- **WHEN** a create omits the choking-hazard field
- **THEN** the response is 422 naming the field and nothing is written

#### Scenario: A solid under six months is refused

- **WHEN** a create gives a fruit a minimum age of 4 months
- **THEN** the response is 422 naming the entry and the rule

#### Scenario: Duplicate identifier

- **WHEN** a create uses an identifier the table already has
- **THEN** the response is 409

#### Scenario: A protected milk feed keeps its category

- **WHEN** an administrator edits breast milk into the dairy category
- **THEN** the response is 409 and the entry is unchanged

### Requirement: Bulk import is validated whole and reports every row

An administrator SHALL be able to import foods from a YAML or CSV file in the table's own
schema. The system SHALL merge the rows into the current table (replacing an entry with the
same identifier, or refusing such an entry when the import is create-only), validate the
merged table whole, and either write one new revision or write nothing. The result SHALL list
the identifiers created, updated, and unchanged and, for every failing row, its row number,
identifier when present, field when known, and a message. A dry run SHALL produce the same
report without writing. A file larger than the limit SHALL be refused.

An import file MAY carry a column or key for any optional micronutrient the table records,
and SHALL be accepted when it carries none. A micronutrient cell left blank SHALL be read as
"not measured", and a cell holding anything other than a blank or a non-negative number
SHALL fail that row with its field named.

#### Scenario: One bad row blocks the file

- **WHEN** a file of five rows has one with a negative iron value
- **THEN** nothing is written and the report names that row, its identifier, the field, and
  the message

#### Scenario: A clean file imports in one revision

- **WHEN** a file of three new rows and one changed existing row is imported
- **THEN** the report lists three created and one updated and one new revision exists

#### Scenario: Dry run writes nothing

- **WHEN** a clean file is imported as a dry run
- **THEN** the report shows what would be created and updated and no revision is added

#### Scenario: A file with micronutrient columns imports

- **WHEN** a file carries zinc and vitamin B12 columns, filled on some rows and blank on
  others
- **THEN** the filled rows import with those values and the blank cells import as not
  measured

#### Scenario: A file without micronutrient columns still imports

- **WHEN** a file carries only the columns the table required before micronutrients existed
- **THEN** it imports unchanged and its foods carry no micronutrient values

#### Scenario: A bad micronutrient cell fails its row

- **WHEN** a row gives `-2` for zinc
- **THEN** nothing is written and the report names that row and the zinc field
