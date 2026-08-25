## Purpose

A registered user identity that owns child profiles and, later, meals and conversations.
This capability exists to establish the authorization anchor: every user-scoped record in
the system belongs to exactly one user, and that ownership is the boundary enforced on
every read and write.

## ADDED Requirements

### Requirement: User account uniqueness

The system SHALL identify each user account by an email address that is unique across all
accounts, and SHALL assign each account a stable, non-sequential identifier used for all
internal references.

#### Scenario: Account created with an unused email

- **WHEN** an account is created with an email address not already registered
- **THEN** the account is persisted with a generated unique identifier and a creation timestamp

#### Scenario: Duplicate email rejected

- **WHEN** an account is created with an email address that already exists
- **THEN** the system rejects the operation with a uniqueness violation
- **AND** no second account is persisted

#### Scenario: Email comparison ignores case

- **WHEN** an account exists for `Parent@Example.com` and creation is attempted for `parent@example.com`
- **THEN** the system treats these as the same address and rejects the duplicate

#### Scenario: Identifiers are not guessable

- **WHEN** two accounts are created in sequence
- **THEN** neither identifier can be derived from the other by incrementing

### Requirement: Ownership is the authorization boundary

Every user-scoped record SHALL carry the identifier of the account that owns it, and the
system SHALL NOT expose any user-scoped record to a request not authenticated as its
owning account.

#### Scenario: Owner reads own records

- **WHEN** an authenticated account requests the child profiles it owns
- **THEN** the system returns exactly those profiles

#### Scenario: Non-owner is refused

- **WHEN** an authenticated account requests a child profile owned by a different account
- **THEN** the system refuses the request
- **AND** the response does not reveal whether that profile exists

#### Scenario: Unauthenticated request is refused

- **WHEN** an unauthenticated request targets any user-scoped record
- **THEN** the system refuses the request and returns no record data

### Requirement: Account deletion removes owned data

When an account is deleted, the system SHALL remove every record owned by that account,
leaving no orphaned user-scoped rows.

#### Scenario: Owned profiles removed with the account

- **WHEN** an account owning child profiles is deleted
- **THEN** those child profiles and their allergy associations are removed
- **AND** no rows referencing the deleted account remain
