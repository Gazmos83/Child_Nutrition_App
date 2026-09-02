## MODIFIED Requirements

### Requirement: The signed-in account is readable

The system SHALL return the signed-in account's id, email, and whether it is an
administrator (see `food-table-admin`), and nothing else about it, to a request with a valid
session.

#### Scenario: Who am I

- **WHEN** a request with a valid session asks for the current account
- **THEN** the response is 200 with exactly the id, the email, and the administrator flag

#### Scenario: Ordinary accounts are not administrators

- **WHEN** an account whose email is not configured as an administrator asks for the
  current account
- **THEN** the administrator flag is false
