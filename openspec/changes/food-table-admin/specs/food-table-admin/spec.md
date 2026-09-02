## Purpose

Lets designated administrators grow and correct the food-composition table at run time —
one food at a time or from a file — without weakening the guarantees the table carries:
explicit safety metadata and provenance on every entry, whole-table validation on every
write, a reproducible version behind every plan, and no deletion of a food a stored record
still names.

## ADDED Requirements

### Requirement: Administrators are designated by configuration

The system SHALL treat an account as an administrator only when its email, compared
case-insensitively, is listed in the `ADMIN_EMAILS` setting. Every administrative route SHALL
refuse an unauthenticated request with 401 and a signed-in non-administrator with 403 and a
message naming the missing role. There SHALL be no route or form that grants the role.

#### Scenario: A listed email is an administrator

- **WHEN** `ADMIN_EMAILS` contains `Parent@Example.com` and that account signs in
- **THEN** its account read reports it as an administrator and administrative routes accept it

#### Scenario: An unlisted account is refused

- **WHEN** an account not in `ADMIN_EMAILS` calls any administrative route
- **THEN** the response is 403 with a message naming administrator access

#### Scenario: No session is refused first

- **WHEN** any administrative route is called without a session
- **THEN** the response is 401

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

#### Scenario: Create with every field

- **WHEN** an administrator posts a new solid with nutrients, category, allergens from the
  vocabulary, the four safety fields, minimum age 6, and a source
- **THEN** the response is 201 and the food appears in the food picker

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

### Requirement: Deactivation hides a food without deleting it

An administrator SHALL be able to deactivate and reactivate a food; nothing SHALL delete a
food. An inactive food SHALL NOT appear in the food picker, SHALL NOT be a candidate for a
meal plan, and SHALL NOT be resolvable by name or identifier through the chat lookup tools,
but SHALL still be retrievable by identifier for pricing feeds already logged with it. The
two protected milk feeds SHALL NOT be deactivatable. Deactivating an already inactive food
SHALL be a no-op that creates no new revision.

#### Scenario: Inactive food leaves the picker and the plan

- **WHEN** an administrator deactivates a food
- **THEN** the picker no longer lists it, a name lookup for it is refused, and no plan
  contains it

#### Scenario: Stored feeds still price

- **WHEN** a feed logged with a food is read after that food was deactivated
- **THEN** the feed still carries its nutrients

#### Scenario: Protected milk feeds stay active

- **WHEN** an administrator tries to deactivate iron-fortified formula
- **THEN** the response is 409 and the food stays active

### Requirement: Bulk import is validated whole and reports every row

An administrator SHALL be able to import foods from a YAML or CSV file in the table's own
schema. The system SHALL merge the rows into the current table (replacing an entry with the
same identifier, or refusing such an entry when the import is create-only), validate the
merged table whole, and either write one new revision or write nothing. The result SHALL list
the identifiers created, updated, and unchanged and, for every failing row, its row number,
identifier when present, field when known, and a message. A dry run SHALL produce the same
report without writing. A file larger than the limit SHALL be refused.

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

### Requirement: Every write is a new table revision that plans can name

Every successful create, edit, deactivation, reactivation, or import SHALL append a new
whole-table revision recording the actor, a summary, and the time, and the served table
version SHALL become `db-<revision>`. Two writes racing for the same next revision SHALL
result in one succeeding and the other refused with 409 asking to reload. A meal plan
generated after a write SHALL carry that revision as its table version.

#### Scenario: Version follows the write

- **WHEN** a food is created on revision 1
- **THEN** the next meal plan's audit record and result name `db-2`

#### Scenario: Concurrent writes do not both land

- **WHEN** two administrators submit writes computed from the same revision
- **THEN** one succeeds and the other receives 409

### Requirement: The seed is the committed file

On a fresh database the migration SHALL create revision 1 from the committed food table file
with a summary naming the file and its version. When no database table has been loaded the
system SHALL serve the committed file and say so in its logs; in the production environment
a failure to load the database table at start SHALL stop the process.

#### Scenario: Fresh database is seeded

- **WHEN** the migrations run on an empty database
- **THEN** revision 1 holds every entry of the committed file

#### Scenario: Development without a database serves the file

- **WHEN** the application starts in the development environment with no reachable database
- **THEN** food lookups still answer from the committed file and the served version is the
  file's version
