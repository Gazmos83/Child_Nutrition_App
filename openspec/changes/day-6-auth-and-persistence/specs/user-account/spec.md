## MODIFIED Requirements

### Requirement: Ownership is the authorization boundary

Every user-scoped record SHALL carry the identifier of the account that owns it, and the
system SHALL NOT expose any user-scoped record to a request not authenticated as its
owning account. The account SHALL be taken from the session (see `authentication`), never
from the request body or path. A refusal for a record owned by another account SHALL be
indistinguishable, in status and body, from the response for a record that does not
exist.

#### Scenario: Owner reads own records

- **WHEN** an authenticated account requests the child profiles it owns
- **THEN** the system returns exactly those profiles

#### Scenario: Non-owner is refused

- **WHEN** an authenticated account requests a child profile owned by a different account
- **THEN** the system refuses the request
- **AND** the response does not reveal whether that profile exists

#### Scenario: Refusal is byte-identical to absence

- **WHEN** an authenticated account reads, replaces, or deletes another account's child
  profile or its feeding log, and separately does the same for a random nonexistent id
- **THEN** each pair of responses has the same status (404) and the same body

#### Scenario: Unauthenticated request is refused

- **WHEN** an unauthenticated request targets any user-scoped record
- **THEN** the system refuses the request and returns no record data

#### Scenario: Every user-scoped operation refuses without a session

- **WHEN** each documented operation on a user-scoped path is called without a session
- **THEN** every one answers 401 with the same fixed message
