## MODIFIED Requirements

### Requirement: Some things are never logged

The system SHALL NOT write to any log record: passwords, password hashes, session tokens,
cookies, request headers, email addresses, or the text of the parent's chat message or the
assistant's answer. The note rows and their kinds SHALL remain in the meal-plan and
gap-detection audit snapshots (hard rule 8).

#### Scenario: Sign-in leaves no credential trace

- **WHEN** a parent registers or signs in
- **THEN** no record contains the password, its hash, the session token, or the email

#### Scenario: Chat message text stays out

- **WHEN** a message is processed
- **THEN** records carry the message's length and the routing decision, not its text
