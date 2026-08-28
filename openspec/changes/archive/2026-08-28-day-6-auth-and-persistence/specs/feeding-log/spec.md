## REMOVED Requirements

### Requirement: The log is client-held today and bounded

**Reason**: authentication and the `feedings` table shipped on Day 6; the log is stored per
child on the account. Replaced by *The log is stored per child and read by its owner*.

**Migration**: the browser posts feeds to `POST /api/children/{child_id}/feedings` and reads
them from `GET /api/children/{child_id}/feedings`; nothing travels in the chat request.

## ADDED Requirements

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
