## ADDED Requirements

### Requirement: Food-table writes are recorded

Every administrative write to the food table SHALL emit one structured log record carrying
the new revision number and a summary of the change, with the account identifier from the
session and never the email. The meal-plan audit record's table version SHALL name a stored
revision (or the committed file's version when the file is being served), so a plan can be
traced to the exact table it was composed from.

#### Scenario: A create is one record

- **WHEN** an administrator creates a food on revision 4
- **THEN** one record names revision 5 and the summary, carries the account identifier, and
  contains no email

#### Scenario: Plans name the revision

- **WHEN** a meal plan is generated while revision 5 is served
- **THEN** its audit record's table version is `db-5`
